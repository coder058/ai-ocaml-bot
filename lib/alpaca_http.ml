(* Thin HTTP helper via curl + Unix.open_process_args_full.
   Keeps dune deps light: only unix + yojson. curl must be on PATH.
   Credential headers are passed through the child's stdin as curl config, not argv. *)

type method_ = GET | POST

let method_str = function GET -> "GET" | POST -> "POST"

let read_all ic =
  let buf = Buffer.create 4096 in
  (try
     while true do
       Buffer.add_string buf (input_line ic);
       Buffer.add_char buf '\n'
     done
   with End_of_file -> ());
  Buffer.contents buf

let quote_config_value value =
  let escaped = Buffer.create (String.length value) in
  let invalid = ref false in
  String.iter
    (function
      | '\n' | '\r' | '\000' -> invalid := true
      | '"' -> Buffer.add_string escaped "\\\""
      | '\\' -> Buffer.add_string escaped "\\\\"
      | c -> Buffer.add_char escaped c)
    value;
  if !invalid then Error "header value contains a forbidden control character"
  else Ok ("\"" ^ Buffer.contents escaped ^ "\"")

let curl_config headers =
  let rec loop lines = function
    | [] -> Ok (String.concat "" (List.rev lines))
    | (name, value) :: rest ->
      match quote_config_value (name ^ ": " ^ value) with
      | Error _ as error -> error
      | Ok encoded -> loop (("header = " ^ encoded ^ "\n") :: lines) rest
  in
  loop [] headers

let credential_env_names =
  [ "APCA_API_KEY_ID"; "ALPACA_API_KEY"; "APCA_API_SECRET_KEY"; "ALPACA_SECRET_KEY" ]

let safe_child_env env =
  let name entry =
    match String.index_opt entry '=' with
    | None -> entry
    | Some i -> String.sub entry 0 i
  in
  env
  |> Array.to_list
  |> List.filter (fun entry -> not (List.mem (name entry) credential_env_names))
  |> Array.of_list

let curl_args ~(meth : method_) ~url ?body () =
  let body_args =
    match body with
    | None -> []
    | Some payload -> [ "--data-binary"; payload ]
  in
  Array.of_list
    ([
       "curl";
       "-sS";
       "-X";
       method_str meth;
       "--max-time";
       "15";
       "-w";
       "\n__HTTP_STATUS__:%{http_code}";
       "--config";
       "-";
     ]
    @ body_args @ [ url ])

(** [request ~meth ~url ~headers ?body ()] runs curl and returns
    [(exit_code, stdout, stderr)]. Headers are [(name, value)] pairs.
    Requires [curl] on PATH. *)
let request ~(meth : method_) ~url ~(headers : (string * string) list)
    ?(body : string option) () : (int * string * string, string) result =
  let headers =
    match body with
    | None -> headers
    | Some _ -> headers @ [ ("Content-Type", "application/json") ]
  in
  match curl_config headers with
  | Error _ as error -> error
  | Ok config_input ->
    let args = curl_args ~meth ~url ?body () in
    try
      let ic, oc, ec =
        Unix.open_process_args_full "curl" args (safe_child_env (Unix.environment ()))
      in
      output_string oc config_input;
      close_out oc;
      let stdout = read_all ic in
      let stderr = read_all ec in
      let status = Unix.close_process_full (ic, oc, ec) in
      let exit_code =
        match status with
        | Unix.WEXITED n -> n
        | Unix.WSIGNALED n -> 128 + n
        | Unix.WSTOPPED n -> 128 + n
      in
      Ok (exit_code, stdout, stderr)
    with
    | Unix.Unix_error (err, fn, _) ->
      Error (Printf.sprintf "curl spawn failed (%s: %s)" fn (Unix.error_message err))
    | Sys_error msg -> Error (Printf.sprintf "curl failed: %s" msg)

(** Split trailing [__HTTP_STATUS__:NNN] marker from curl -w output. *)
let split_status stdout =
  let marker = "__HTTP_STATUS__:" in
  try
    let stdout = String.trim stdout in
    let i = String.rindex stdout '\n' in
    let line = String.sub stdout (i + 1) (String.length stdout - i - 1) in
    let body = String.sub stdout 0 i in
    if
      String.length line >= String.length marker
      && String.sub line 0 (String.length marker) = marker
    then
      let code_s =
        String.sub line (String.length marker)
          (String.length line - String.length marker)
      in
      (body, int_of_string (String.trim code_s))
    else (stdout, -1)
  with _ -> (stdout, -1)

(** GET JSON from [url] with Alpaca key headers. Returns parsed Yojson or Error. *)
let get_json ~url ~key_id ~secret : (Yojson.Safe.t, string) result =
  let headers =
    [
      ("APCA-API-KEY-ID", key_id);
      ("APCA-API-SECRET-KEY", secret);
      ("Accept", "application/json");
    ]
  in
  match request ~meth:GET ~url ~headers () with
  | Error e -> Error e
  | Ok (exit_code, stdout, stderr) ->
    if exit_code <> 0 then
      Error
        (Printf.sprintf "curl exit %d: %s" exit_code
           (if stderr = "" then "(no stderr)" else String.trim stderr))
    else
      let body, http = split_status stdout in
      if http < 200 || http >= 300 then
        Error (Printf.sprintf "HTTP %d: %s" http (String.trim body))
      else
        (try Ok (Yojson.Safe.from_string body)
         with Yojson.Json_error msg -> Error ("JSON parse: " ^ msg))

let get_public_json ~url : (Yojson.Safe.t, string) result =
  match request ~meth:GET ~url ~headers:[ ("Accept", "application/json") ] () with
  | Error e -> Error e
  | Ok (exit_code, stdout, stderr) ->
    if exit_code <> 0 then Error (Printf.sprintf "curl exit %d: %s" exit_code (String.trim stderr))
    else
      let body, http = split_status stdout in
      if http < 200 || http >= 300 then Error (Printf.sprintf "HTTP %d: %s" http (String.trim body))
      else
        (try Ok (Yojson.Safe.from_string body)
         with Yojson.Json_error msg -> Error ("JSON parse: " ^ msg))

(** POST JSON. Same auth headers. Only the paper broker calls this. *)
let post_json ~url ~key_id ~secret ~body : (Yojson.Safe.t, string) result =
  let headers =
    [
      ("APCA-API-KEY-ID", key_id);
      ("APCA-API-SECRET-KEY", secret);
      ("Accept", "application/json");
    ]
  in
  match request ~meth:POST ~url ~headers ~body () with
  | Error e -> Error e
  | Ok (exit_code, stdout, stderr) ->
    if exit_code <> 0 then
      Error
        (Printf.sprintf "curl exit %d: %s" exit_code
           (if stderr = "" then "(no stderr)" else String.trim stderr))
    else
      let resp, http = split_status stdout in
      if http < 200 || http >= 300 then
        Error (Printf.sprintf "HTTP %d: %s" http (String.trim resp))
      else
        (try Ok (Yojson.Safe.from_string resp)
         with Yojson.Json_error msg -> Error ("JSON parse: " ^ msg))
