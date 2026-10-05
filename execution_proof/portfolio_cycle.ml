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
