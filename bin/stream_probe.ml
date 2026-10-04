(* Read-only local fanout probe. This executable has no broker/order module. *)

let socket_path = "/home/ubuntu/jsbot-paper-state/alpaca-hot.sock"
(* SOURCE: the private capture service's local datagram address on Dublin. *)
let lock_path = "/home/ubuntu/jsbot-paper-state/alpaca-hot.lock"
(* SOURCE: a persistent lock file arbitrates ownership of the diagnostic socket. *)

let member name = function
  | `Assoc fields -> List.assoc_opt name fields
  | _ -> None

let string_field name value =
  match member name value with Some (`String text) -> text | _ -> ""

let int_field name value =
  match member name value with
  | Some (`Int number) -> Some number
  | _ -> None

let main () =
  let lock_fd = Unix.openfile lock_path [Unix.O_CREAT; Unix.O_RDWR] 0o600 in
  Unix.lockf lock_fd Unix.F_LOCK 0;
  let socket = Unix.socket Unix.PF_UNIX Unix.SOCK_DGRAM 0 in
  let bound = ref false in
  Fun.protect ~finally:(fun () ->
    Unix.close socket;
    if !bound && Sys.file_exists socket_path then Unix.unlink socket_path;
    Unix.lockf lock_fd Unix.F_ULOCK 0;
    Unix.close lock_fd) (fun () ->
    (* Lock ownership makes a leftover socket from a crashed instance stale. *)
    if Sys.file_exists socket_path then Unix.unlink socket_path;
    Unix.bind socket (Unix.ADDR_UNIX socket_path);
    bound := true;
    Unix.chmod socket_path 0o600;
    (* SOURCE: owner-only socket in the private VPS state directory. *)
    (* GUESS: # UNCALIBRATED GUESS — 8 KiB bounds a compact quote/bar frame;
       a later executable must reject truncation explicitly. *)
    let buffer = Bytes.create 8192 in
    let active_session = ref None and last_sequence = ref 0 in
    while true do
      let length, _ = Unix.recvfrom socket buffer 0 (Bytes.length buffer) [] in
      let record =
        try Yojson.Safe.from_string (Bytes.sub_string buffer 0 length)
        with Yojson.Json_error _ -> failwith "invalid or truncated hot datagram" in
      let event = Option.value (member "event" record) ~default:`Null in
      let session = string_field "sessionId" record in
      let sequence = int_field "hotSequence" record in
      let received_ns = int_field "receivedAtNs" record in
      (match sequence, received_ns with
       | Some sequence, Some received_ns when session <> "" && sequence > 0 && received_ns > 0 ->
         if !active_session <> Some session then (
           active_session := Some session;
           (* The probe may attach mid-session; continuity is provable only
              from its first observed datagram onward. *)
           last_sequence := sequence - 1;
           Printf.printf "HOT_SESSION session=%s first_sequence=%d\n%!" session sequence);
         if sequence <> !last_sequence + 1 then
           failwith (Printf.sprintf "hot datagram gap expected=%d received=%d" (!last_sequence + 1) sequence);
         last_sequence := sequence;
         let bridge_ms = Unix.gettimeofday () *. 1_000. -.
           float_of_int received_ns /. 1_000_000. in
         Printf.printf "HOT_BRIDGE type=%s session=%s seq=%d bridge_ms=%.3f event_time=%s\n%!"
           (string_field "T" event) session sequence bridge_ms (string_field "t" event)
       | _ -> failwith "hot datagram lacks required session, sequence, or receive timestamp")
    done)

let () =
  Sys.set_signal Sys.sigterm (Sys.Signal_handle (fun _ -> raise Sys.Break));
  Sys.set_signal Sys.sigint (Sys.Signal_handle (fun _ -> raise Sys.Break));
  try main () with Sys.Break -> print_endline "HOT_PROBE_STOPPED"
