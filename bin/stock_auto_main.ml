open Paper_market
(* Closed-candle stock scheduler delegates all submission and reconciliation to
   the serialized durable stock router. No network POST is implemented here. *)
let state_dir=Option.value ~default:"/home/ubuntu/jsbot-paper-state" (Sys.getenv_opt "PAPER_STATE_DIR")
let path name=Filename.concat state_dir name
let field=Paper_broker.member
let text name row=Option.value ~default:"" (Paper_broker.string (field name row))
let unwrap=function Ok value->value|Error message->failwith message
let atomic filename value =
  let temporary=filename ^ ".tmp" in
  (* SOURCE: match the private durable router's state permissions. *)
  let fd=Unix.openfile temporary [Unix.O_CREAT;Unix.O_WRONLY;Unix.O_TRUNC] 0o640 in
  let out=Unix.out_channel_of_descr fd in
  Fun.protect ~finally:(fun ()->close_out_noerr out) (fun ()->
    output_string out (Yojson.Safe.to_string value ^ "\n");flush out;Unix.fsync fd);
  Unix.rename temporary filename;
  let directory=Unix.openfile state_dir [Unix.O_RDONLY] 0 in
  Fun.protect ~finally:(fun ()->Unix.close directory) (fun ()->Unix.fsync directory)
let orders ()=let file=path "stock-paper-ledger.json" in
  if not (Sys.file_exists file) then [] else match field "orders" (Yojson.Safe.from_file file) with
    | Some (`List rows)->rows|_->failwith "stock ledger unreadable; no ownership reset"
let owned ticker rows=List.fold_left (fun total row->
  if text "symbol" row<>ticker then total else match field "broker" row with
    | Some broker -> let qty=unwrap (Exact_decimal.of_string (text "filled_qty" broker)) in
      if text "side" row="buy" then (
        if total>Int64.sub Int64.max_int qty then failwith "stock ownership overflow";
        Int64.add total qty)
      else if qty>total then failwith "stock exit exceeds ownership" else Int64.sub total qty
    | None->total) Exact_decimal.zero rows
let pending ticker rows=List.exists (fun row->text "symbol" row=ticker && text "state" row="pending") rows
let managed ticker rows=match List.find_opt (fun row->text "symbol" row=ticker && text "side" row="buy") (List.rev rows) with
  | Some row when field "analysisEvidence" row<>None -> Some row
  | _->None
let router args =
  let executable=Filename.concat (Filename.dirname Sys.executable_name) "stock_paper_main.exe" in
  let sink=Unix.openfile "/dev/null" [Unix.O_WRONLY] 0 in
  Fun.protect ~finally:(fun ()->Unix.close sink) (fun ()->
    let pid=Unix.create_process executable (Array.of_list (executable::args)) Unix.stdin sink sink in
    match snd (Unix.waitpid [] pid) with Unix.WEXITED 0->true|_->false)
let run ()=
  if not (router ["--check"]) then failwith "stock reconciliation/preflight health check failed";
  let now=Unix.gettimeofday () in
  let execute=Array.exists ((=) "--execute") Sys.argv in
  let armed=execute && Sys.getenv_opt "PAPER_ORDERS"=Some "1" &&
    Sys.getenv_opt "STOCK_PAPER_ORDERS"=Some "1" && Sys.getenv_opt "STOCK_AUTO_ORDERS"=Some "1" in
  let new_entries=armed && Sys.getenv_opt "STOCK_AUTO_NEW_ENTRIES"=Some "1" in
  let document=try Yojson.Safe.from_file (path "market-pipeline.json") with _->`Null in
  let signals_result=Stock_policy.signals ~now document in
  let signals=match signals_result with Ok signals->signals|Error _->[] in
  let rows=ref (orders ()) in
  let abstentions=ref [] and previews=ref [] and invoked=ref 0 in
  let block symbol reason=abstentions:=`Assoc ["symbol",`String symbol;"reason",`String reason]:: !abstentions in
  let clock=unwrap (Paper_broker.get "/v2/clock") in
  let session=Paper_broker.bool (field "is_open" clock)=Some true in
  let transmit ticker side amount cid reason evidence =
    let intent=path ("stock-auto-intent-" ^ cid ^ ".json") in
    atomic intent evidence;
    let ok=router [if side="buy" then "--buy" else "--sell";ticker;"--amount";amount;
      "--client-id";cid;"--reason";reason;"--evidence-file";intent;"--execute"] in
    incr invoked;rows:=orders ();
    if not ok then block ticker "Serialized stock router rejected or could not verify this request; inspect durable events before retrying" in
  let tickers=List.sort_uniq String.compare (List.map (fun row->text "symbol" row) !rows) in
  (* SOURCE: owned exits take priority over new entries. Manual stock positions
     have no managed entry evidence and must not be adopted by this scheduler. *)
  List.iter (fun ticker->
    if owned ticker !rows>Exact_decimal.zero then match managed ticker !rows with
      | None->block ticker "Existing stock inventory has no managed policy entry; no automatic adoption"
      | Some _ when pending ticker !rows->block ticker "Pending owned stock order must reconcile before any exit or entry"
      | Some entry ->
        let evidence=Option.get (field "analysisEvidence" entry) in
        let stop=Paper_broker.float (field "invalidationLevel" evidence) in
        let frame=text "frame" evidence in
        (match stop with None->block ticker "Managed entry invalidation missing"|Some stop->
          if not session then block ticker "Regular stock session closed; local stop cannot execute outside this session"
          else match Paper_stock_broker.quotes [ticker] with
            | Error _->block ticker "Owned exit quote read unavailable"
            | Ok quotes->(match Stock_policy.quote ~now:(Unix.gettimeofday ()) ~symbol:ticker quotes with
              | Error reason->block ticker reason
              | Ok quote->(match Stock_policy.exit_reason ~now:(Unix.gettimeofday ()) ~stop ~frame ~symbol:ticker quote document with
                | None->()
                | Some reason when not armed->block ticker (reason ^ "; automatic paper exit gate disabled")
                | Some reason->
                  let cid=Stock_policy.client_id [text "clientOrderId" entry;"exit";quote.timestamp] in
                  if not (List.exists (fun row->text "clientOrderId" row=cid) !rows) then
                    transmit ticker "sell" (Exact_decimal.to_string (owned ticker !rows)) cid reason
                      (`Assoc ["symbol",`String ticker;"side",`String "sell";"clientOrderId",`String cid;
                        "originEntryId",`String (text "clientOrderId" entry);"policy",`String "trend_candle_confluence_v1";
                        "frame",`String frame;"invalidationLevel",`Float stop;"reason",`String reason]))))
  ) tickers;
  (match signals_result with Error reason->block "all" reason|Ok _->());
  (* GUESS: # UNCALIBRATED GUESS — reuse the crypto experiment's ten-position
     operational limit for the stock paper cohort; not a fitted allocation. *)
  List.iter (fun (signal:Stock_policy.signal)->
    let ticker=signal.symbol and cid=Stock_policy.entry_id signal in
    previews:=`Assoc ["symbol",`String ticker;"frame",`String signal.frame;"bar",`String signal.bar;
      "invalidationLevel",`Float signal.stop;"clientOrderId",`String cid]:: !previews;
    if not session then block ticker "Regular equity session is closed; no queued entries"
    else if not new_entries then block ticker "Automatic stock new-entry gate is disabled; this candidate is observation only"
    else if List.exists (fun row->text "clientOrderId" row=cid) !rows then block ticker "This exact frame/bar entry identity was already attempted"
    else if pending ticker !rows then block ticker "Pending owned order must reconcile"
    else if owned ticker !rows<>Exact_decimal.zero then block ticker "One owned position per instrument; other frames do not scale in"
    else if List.length (List.filter (fun symbol->owned symbol !rows>Exact_decimal.zero || pending symbol !rows)
      (List.sort_uniq String.compare (List.map (fun row->text "symbol" row) !rows)))>=Multi_paper.max_open_tickets then
      block ticker "Stock cohort operational position limit reached"
    else
      let reason="Rising EMA20/EMA50 and bullish candle shape on a closed stock bar; exploratory paper policy" in
      let analysis=`Assoc ["asOf",Option.value ~default:`Null (field "asOf" document);
        "retrievedAt",Option.value ~default:`Null (field "retrievedAt" document);
        "policy",`String "trend_candle_confluence_v1";"orderAuthority",`Bool false;
        "markets",`List [`Assoc ["symbol",`String ticker;"venue",`String "Alpaca equities";
          "frames",`Assoc [signal.frame,signal.reading]]]] in
      transmit ticker "buy" (Exact_decimal.to_string (unwrap (Exact_decimal.of_float Multi_paper.entry_usd))) cid reason
        (`Assoc ["symbol",`String ticker;"side",`String "buy";"clientOrderId",`String cid;
          "policy",`String "trend_candle_confluence_v1";"frame",`String signal.frame;
          "signalBar",`String signal.bar;"invalidationLevel",`Float signal.stop;
          "reading",signal.reading;"analysis",analysis;"reason",`String reason])
  ) signals;
  let owned_positions=List.filter_map (fun ticker->
    let qty=owned ticker !rows and unresolved=pending ticker !rows in
    if qty=Exact_decimal.zero && not unresolved then None else
    let origin=managed ticker !rows in
    Some (`Assoc ["symbol",`String ticker;"quantity",`String (Exact_decimal.to_string qty);
      "managed",`Bool (origin<>None);"pending",`Bool unresolved;
      "frame",(match Option.bind origin (field "analysisEvidence") with Some evidence->
        Option.value ~default:`Null (field "frame" evidence)|None->`Null)])
  ) (List.sort_uniq String.compare (List.map (fun row->text "symbol" row) !rows)) in
  let result=`Assoc ["asOf",`String (Multi_paper.observed_stamp (Unix.gettimeofday ()));
    "mode",`String (if armed then "PAPER_EXPERIMENT" else "OBSERVE");
    "automaticStrategy",`Bool true;"newEntriesEnabled",`Bool new_entries;
    "sessionOpen",`Bool session;"entryUsd",`Float Multi_paper.entry_usd;
    "maxOpenPositions",`Int Multi_paper.max_open_tickets;"eligibleLongSignals",`Int (List.length signals);
    "routerInvocations",`Int !invoked;"candidates",`List (List.rev !previews);
    "ownedPositions",`List owned_positions;
    "abstentions",`List (List.rev !abstentions);"winProbability",`Null;
    "stopHandling",`String "Local IEX-bid invalidation or origin-frame EMA reversal; regular session only; no resting stop"] in
  atomic (path "stock-auto.json") result;
  print_endline (Yojson.Safe.to_string (`Assoc ["sessionOpen",`Bool session;"candidates",`Int (List.length signals);"routerInvocations",`Int !invoked]))
let ()=
  let fd=Unix.openfile (path "stock-auto.lock") [Unix.O_CREAT;Unix.O_WRONLY] 0o640 in
  Fun.protect ~finally:(fun ()->Unix.close fd) (fun ()->try Unix.lockf fd Unix.F_TLOCK 0;run ()
    with error->prerr_endline ("stock auto: " ^ Printexc.to_string error);exit 1)
