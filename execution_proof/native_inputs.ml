(* Read-only original-input replay before automatic entry preflight.
   The verifier receives market evidence only, never credentials. *)
let verify ~state_dir ~as_of ~venue ~symbol ~frame ~reading =
  let request=`Assoc ["asOf",`String as_of;"venue",`String venue;
    "symbol",`String symbol;"frame",`String frame;"reading",reading] in
  (* SOURCE: OCaml private temporary-file permissions; removed after verification. *)
  let file,output=Filename.open_temp_file ~perms:0o600 "native-input-request-" ".json" in
  Fun.protect ~finally:(fun ()->close_out_noerr output;try Sys.remove file with _->()) (fun ()->
    output_string output (Yojson.Safe.to_string request);close_out output;
    let script=Filename.concat (Filename.dirname Sys.executable_name)
      "../../../research/verify_decision_input.py" in
    (* SOURCE: verification needs UTC and Python's UTF-8 locale only. Do not
       inherit the execution process's Alpaca credentials into this reader. *)
    let channels=Unix.open_process_args_full "/usr/bin/python3"
      [|"/usr/bin/python3";script;"--state-dir";state_dir;"--request-file";file|]
      [|"TZ=UTC";"LC_ALL=C.UTF-8"|] in
    let input,_,_=channels in
    let response=try Some (Yojson.Safe.from_string (input_line input)) with _->None in
    let status=Unix.close_process_full channels in
    match response,status with
    | Some (`Assoc fields as value),Unix.WEXITED 0 when List.assoc_opt "verified" fields=Some (`Bool true)->Ok value
    | Some (`Assoc fields),_ -> Error (match List.assoc_opt "reason" fields with
        | Some (`String reason)->"Native candidate proof rejected: " ^ reason
        | _->"Native candidate proof rejected")
    | _->Error "Native candidate proof could not be verified")
