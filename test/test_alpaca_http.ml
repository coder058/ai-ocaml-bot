open Paper_market

let failures = ref 0

let check name passed =
  if passed then Printf.printf "  ok   %s\n" name
  else (
    incr failures;
    Printf.printf "  FAIL %s\n" name)

let contains haystack needle =
  let haystack_length = String.length haystack in
  let needle_length = String.length needle in
  let rec search start =
    if start + needle_length > haystack_length then false
    else if String.sub haystack start needle_length = needle then true
    else search (start + 1)
  in
  search 0

let env_names =
  [ "APCA_API_KEY_ID"; "ALPACA_API_KEY"; "APCA_API_SECRET_KEY"; "ALPACA_SECRET_KEY" ]

let restore_env name value =
  match value with
  | Some value -> Unix.putenv name value
  | None -> Unix.putenv name ""

let read_file path =
  let ic = open_in_bin path in
  Fun.protect ~finally:(fun () -> close_in_noerr ic) (fun () ->
      really_input_string ic (in_channel_length ic))

let with_fake_curl test =
  (* SYNTHETIC fake-curl executable records argv and stdin without making a network call. *)
  let directory = Filename.temp_file "synthetic-curl-" ".dir" in
  Sys.remove directory;
  Unix.mkdir directory 0o700;
  let curl_path = Filename.concat directory "curl" in
  let args_path = Filename.concat directory "args" in
  let config_path = Filename.concat directory "config" in
  let credential_presence_path = Filename.concat directory "credential-presence" in
  let script =
    "#!/bin/sh\n"
    ^ "printf '%s\\n' \"$@\" > \"$SYNTHETIC_CAPTURE_DIR/args\"\n"
    ^ "for name in APCA_API_KEY_ID ALPACA_API_KEY APCA_API_SECRET_KEY ALPACA_SECRET_KEY; do\n"
    ^ "  eval \\\"present=\\${$name+x}\\\"\n"
    ^ "  if [ \\\"$present\\\" = x ]; then printf '%s=present\\n' \"$name\"; "
    ^ "else printf '%s=absent\\n' \"$name\"; fi\n"
    ^ "done > \"$SYNTHETIC_CAPTURE_DIR/credential-presence\"\n"
    ^ "cat > \"$SYNTHETIC_CAPTURE_DIR/config\"\n"
    ^ "printf '{\"ok\":true}\\n__HTTP_STATUS__:200\\n'\n"
  in
  let oc = open_out_bin curl_path in
  output_string oc script;
  close_out oc;
  (* SOURCE: POSIX 0700 grants execute access only to the file owner. *)
  Unix.chmod curl_path 0o700;
  let old_path = Sys.getenv_opt "PATH" in
  let old_capture_dir = Sys.getenv_opt "SYNTHETIC_CAPTURE_DIR" in
  let old_credentials = List.map (fun name -> name, Sys.getenv_opt name) env_names in
  Fun.protect
    ~finally:(fun () ->
      (match old_path with
       | Some path -> Unix.putenv "PATH" path
       | None -> Unix.putenv "PATH" "");
      restore_env "SYNTHETIC_CAPTURE_DIR" old_capture_dir;
      List.iter (fun (name, value) -> restore_env name value) old_credentials;
      List.iter
        (fun path -> if Sys.file_exists path then Sys.remove path)
        [ args_path; config_path; credential_presence_path; curl_path ];
      Unix.rmdir directory)
    (fun () ->
      let original_path = match old_path with Some path -> path | None -> "/usr/bin:/bin" in
      Unix.putenv "PATH" (directory ^ ":" ^ original_path);
      Unix.putenv "SYNTHETIC_CAPTURE_DIR" directory;
      List.iter (fun name -> Unix.putenv name ("SYNTHETIC-" ^ name)) env_names;
      test ~args_path ~config_path ~credential_presence_path)

let () =
  Printf.printf "alpaca_http credential handling\n";
  (* SYNTHETIC fixture values only; never use real Alpaca credentials in tests. *)
  let secret = "SYNTHETIC-APCA-SECRET-DO-NOT-USE" in
  let key_id = "SYNTHETIC-APCA-ID-DO-NOT-USE" in
  with_fake_curl (fun ~args_path ~config_path ~credential_presence_path ->
      match
        Alpaca_http.request ~meth:Alpaca_http.GET
          ~url:"https://paper-api.alpaca.markets/v2/account"
          ~headers:[ ("APCA-API-KEY-ID", key_id); ("APCA-API-SECRET-KEY", secret) ] ()
      with
      | Error error -> check ("synthetic request succeeds: " ^ error) false
      | Ok (exit_code, stdout, _) ->
        let args = read_file args_path in
        let config = read_file config_path in
        let credential_presence = read_file credential_presence_path in
        check "synthetic curl exit succeeds" (exit_code = 0);
        check "synthetic HTTP status marker returned" (contains stdout "__HTTP_STATUS__:200");
        check "API key header arrives via stdin config" (contains config key_id);
        check "API secret header arrives via stdin config" (contains config secret);
        check "credentials absent from curl argv"
          (not (contains args key_id || contains args secret));
        check "credential variables absent from child environment"
          (not (contains credential_presence "=present")));
  let old_gate = Sys.getenv_opt "PAPER_ORDERS" in
  Unix.putenv "PAPER_ORDERS" "";
  (match Paper_broker.submit_ioc ~side:"buy" ~qty:0.001
           ~limit_price:20_000. ~client_order_id:"SYNTHETIC-ORDER" with
   | Error _ -> check "paper order gate refuses when unarmed" true
   | Ok _ -> check "paper order gate refuses when unarmed" false);
  (match old_gate with Some x -> Unix.putenv "PAPER_ORDERS" x
   | None -> Unix.putenv "PAPER_ORDERS" "");
  Unix.putenv "PAPER_ORDERS" "1";
  with_fake_curl (fun ~args_path ~config_path ~credential_presence_path:_ ->
    match Paper_broker.submit_ioc ~side:"buy" ~qty:0.001
            ~limit_price:20_000. ~client_order_id:"SYNTHETIC-ORDER" with
    | Error e -> check ("synthetic paper submit: " ^ e) false
    | Ok _ ->
      let args = read_file args_path and config = read_file config_path in
      check "submit targets only paper order URL"
        (contains args "https://paper-api.alpaca.markets/v2/orders"
         && not (contains args "https://api.alpaca.markets"));
      check "submit includes client order id"
        (contains args "SYNTHETIC-ORDER");
      check "submit secrets absent from argv"
        (not (contains args "SYNTHETIC-APCA-SECRET-DO-NOT-USE"));
      check "submit sends secret in stdin config"
        (contains config "SYNTHETIC-APCA_API_SECRET_KEY"));
  (match old_gate with Some x -> Unix.putenv "PAPER_ORDERS" x
   | None -> Unix.putenv "PAPER_ORDERS" "");
  (match
     Alpaca_http.curl_config [ ("X-Test", "safe\r\nInjected: true") ]
   with
   | Error _ -> check "reject CRLF header injection" true
   | Ok _ -> check "reject CRLF header injection" false);
  if !failures = 0 then (
    Printf.printf "all alpaca_http checks passed\n";
    exit 0)
  else (
    Printf.printf "%d alpaca_http check(s) FAILED\n" !failures;
    exit 1)
