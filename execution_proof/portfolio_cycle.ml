(* Both current Alpaca routers share one account and private state directory.
   Serialize reconciliation/account/position checks through durable intent and
   broker acknowledgement. This does not add loss/correlation risk limits. *)
let run ~state_dir action =
  (* SOURCE: same private state/permissions as the existing cohort locks. *)
  let fd=Unix.openfile (Filename.concat state_dir "alpaca-paper-portfolio.lock")
    [Unix.O_CREAT;Unix.O_WRONLY] 0o640 in
  Fun.protect ~finally:(fun ()->Unix.close fd) (fun ()->
    (try Unix.lockf fd Unix.F_TLOCK 0 with
     | Unix.Unix_error ((Unix.EACCES|Unix.EAGAIN),_,_) ->
       failwith "Alpaca paper portfolio cycle is busy; no router HTTP work performed");
    action ())

(* SOURCE: existing durable pending states represent accepted, nonterminal or
   uncertain orders. Their capital/inventory outcome is not safely reusable.
   Invoke under the shared account lock after own-cohort reconciliation and
   before persisting a new buy. This never suppresses managed owned exits. *)
let entry_clear ~state_dir =
  let read name check =
    let file=Filename.concat state_dir name in
    try
      if Sys.file_exists file then check (Yojson.Safe.from_file file) else Ok ()
    with _ -> Error (name ^ " cannot be read; new exposure blocked") in
  let stock document =
    let field=Paper_market.Paper_broker.member in
    let text name row=Paper_market.Paper_broker.string (field name row) in
    match field "orders" document with
    | Some (`List rows) ->
      List.fold_left (fun result row -> Result.bind result (fun () ->
        match text "clientOrderId" row,text "side" row,text "state" row with
        | Some cid,Some side,Some state when String.starts_with ~prefix:"aibotstk" cid &&
            List.mem side ["buy";"sell"] && List.mem state ["pending";"resolved";"rejected"] ->
          if state="pending" then Error ("Unresolved owned stock order blocks new exposure: " ^ cid)
          else Ok ()
        | _ -> Error "Stock reservation ledger has invalid identity/state; new exposure blocked"
      )) (Ok ()) rows
    | _ -> Error "Stock reservation ledger schema invalid; new exposure blocked" in
  let crypto document =
    Result.bind (Paper_market.Multi_paper.of_json document) (fun state ->
      match List.find_opt (fun (ticket:Paper_market.Multi_paper.ticket)->ticket.pending<>None) state.tickets with
      | Some ticket -> Error ("Unresolved owned crypto order blocks new exposure: " ^
          (Option.get ticket.pending).client_id)
      | None -> Ok ()) in
  Result.bind (read "stock-paper-ledger.json" stock) (fun () ->
    read "multi-paper-ledger.json" crypto)
