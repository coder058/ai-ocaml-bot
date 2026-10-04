open Paper_market

(* JSON in -> descriptive JSON out. There is no broker call or order path. *)
let () =
  try
    let document = Yojson.Safe.from_channel stdin in
    match Frame_analysis.analyze document with
    | Ok result -> print_endline (Yojson.Safe.to_string result)
    | Error error -> prerr_endline error; exit 1
  with error -> prerr_endline (Printexc.to_string error); exit 1
