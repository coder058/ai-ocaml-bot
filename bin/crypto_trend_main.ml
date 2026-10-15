open Paper_market
(* BTC/USD month-end trend executor (crypto_monthly_trend_v1). Owns only the
   quantity its own fills created, never adopts other BTC, writes each request
   durably before POST and reconciles before any new decision. *)
let state_dir=Option.value ~default:"/home/ubuntu/jsbot-paper-state" (Sys.getenv_opt "PAPER_STATE_DIR")
let path name=Filename.concat state_dir name
let field=Paper_broker.member
let text name row=Option.value ~default:"" (Paper_broker.string (field name row))
let unwrap=function Ok value->value|Error message->failwith message
let ledger_path=path Crypto_trend_broker.ledger_name
let atomic filename value =
  let temporary=filename ^ ".tmp" in
  let fd=Unix.openfile temporary [Unix.O_CREAT;Unix.O_WRONLY;Unix.O_TRUNC] 0o640 in
  let out=Unix.out_channel_of_descr fd in
  Fun.protect ~finally:(fun ()->close_out_noerr out) (fun ()->
    output_string out (Yojson.Safe.to_string value ^ "\n");flush out;Unix.fsync fd);
  Unix.rename temporary filename;
  let directory=Unix.openfile state_dir [Unix.O_RDONLY] 0 in
  Fun.protect ~finally:(fun ()->Unix.close directory) (fun ()->Unix.fsync directory)
let journal kind cid detail =
  let row=`Assoc ["at",`String (Multi_paper.observed_stamp (Unix.gettimeofday ()));"kind",`String kind;
    "clientOrderId",`String cid;"policy",`String Monthly_trend.crypto_policy;"detail",detail] in
  let fd=Unix.openfile (path "crypto-trend-events.jsonl") [Unix.O_CREAT;Unix.O_WRONLY;Unix.O_APPEND] 0o640 in
  let out=Unix.out_channel_of_descr fd in
  Fun.protect ~finally:(fun ()->close_out_noerr out) (fun ()->
    output_string out (Yojson.Safe.to_string row ^ "\n");flush out;Unix.fsync fd)
let read_orders ()=
  if not (Sys.file_exists ledger_path) then [] else
  match field "orders" (Yojson.Safe.from_file ledger_path) with
  | Some (`List rows)->rows | _->failwith "crypto trend ledger is invalid; refusing ownership reset"
let save rows=atomic ledger_path (`Assoc ["orders",`List rows])
let replace name value=function `Assoc fields->`Assoc ((name,value)::List.remove_assoc name fields)
  | _->failwith "invalid crypto trend order"
let terminal broker=List.mem (text "status" broker) ["filled";"canceled";"expired";"rejected"]
let filled row=match field "broker" row with
  | Some broker->unwrap (Exact_decimal.of_string (Option.value ~default:"0" (Paper_broker.string (field "filled_qty" broker))))
  | None->Exact_decimal.zero
let validate_broker row broker =
  if text "client_order_id" broker<>text "clientOrderId" row ||
     not (Paper_crypto_broker.same_symbol (text "symbol" broker) Crypto_trend_broker.symbol) ||
     text "side" broker<>text "side" row then failwith "crypto trend broker identity mismatch";
  let qty=filled (replace "broker" broker row) in
  if qty<filled row then failwith "crypto trend cumulative fills decreased";
  let requested=unwrap (Exact_decimal.of_string (text "qty" (Option.get (field "request" row)))) in
  if qty>requested then failwith "crypto trend overfill"
let owned rows=List.fold_left (fun total row->
  let qty=filled row in
  if text "side" row="buy" then Int64.add total qty
  else if qty>total then failwith "crypto trend exits exceed owned fills" else Int64.sub total qty) Exact_decimal.zero rows
let cash_flow rows=List.fold_left (fun total row->match field "broker" row with
  | Some broker->(match Paper_broker.float (field "filled_avg_price" broker) with
    | Some price->let value=Exact_decimal.to_float (filled row)*.price in
      if text "side" row="buy" then total-.value else total+.value
    | None->total)
  | None->total) 0. rows
let run ()=
  let now=Unix.gettimeofday () in
  let t=Unix.gmtime now in
  let today=(t.tm_year+1900,t.tm_mon+1,t.tm_mday) in
  let armed=Array.exists ((=) "--execute") Sys.argv && Sys.getenv_opt "PAPER_ORDERS"=Some "1" &&
    Sys.getenv_opt "CRYPTO_TREND_ORDERS"=Some "1" in
  let rows=ref (read_orders ()) in
  let ids=List.map (text "clientOrderId") !rows in
  if List.length ids<>List.length (List.sort_uniq String.compare ids) then failwith "duplicate crypto trend IDs";
  List.iter (fun row->
    if not (String.starts_with ~prefix:Crypto_trend_broker.prefix (text "clientOrderId" row)) ||
       not (List.mem (text "side" row) ["buy";"sell"]) ||
       not (List.mem (text "state" row) ["pending";"resolved";"rejected"]) then
      failwith "invalid crypto trend ledger row";
    Option.iter (validate_broker row) (field "broker" row)) !rows;
  (* Reconcile every pending request before any decision. *)
  rows:=List.map (fun row->
    if text "state" row<>"pending" then row else
    match Paper_broker.order_by_client_id (text "clientOrderId" row) with
    | Error error->journal "LOOKUP_UNCERTAIN" (text "clientOrderId" row) (`String error);row
    | Ok broker->validate_broker row broker;
      replace "state" (`String (if terminal broker then "resolved" else "pending")) (replace "broker" broker row)) !rows;
  save !rows;
  let notes=ref [] in
  let note status detail=notes:=`Assoc (("status",`String status)::detail):: !notes in
  let own=owned !rows in
  let asset=unwrap (Paper_crypto_broker.asset Crypto_trend_broker.symbol) in
  let step=unwrap (Exact_decimal.of_string asset.step_text) in
  let minimum=unwrap (Exact_decimal.of_float asset.minimum) in
  let broker_qty=unwrap (Paper_crypto_broker.quantity_exact Crypto_trend_broker.symbol
    (unwrap (Paper_crypto_broker.positions ()))) in
  let quote=unwrap (Paper_crypto_broker.quote Crypto_trend_broker.symbol) in
  let (y,m,_)=today in
  let start=Printf.sprintf "%04d-%02d-01" (y-1) m in
  let reading=match Crypto_trend_broker.daily_bars ~start with
    | Error e->Error e
    | Ok bars->if t.tm_mday=1 && t.tm_hour<12 then Error "Month-end daily bar may still be open before 12:00 UTC on the 1st"
      else Result.map (fun r->r,bars) (Monthly_trend.decide_monthly ~today bars) in
  (* Fee debits can only lower broker BTC below own fills; anything above own
     fills plus dust belongs to another owner and blocks new exposure. *)
  let external_qty=if broker_qty>own then Int64.sub broker_qty own else Exact_decimal.zero in
  let other_owner=external_qty>=minimum || Sys.file_exists (path "pending") || Sys.file_exists (path "owned") ||
    (match (try Some (Yojson.Safe.from_file (path "multi-paper-ledger.json")) with _->None) with
     | Some doc->(match Multi_paper.of_json doc with
       | Ok state->Multi_paper.ticket_for state "BTC/USD"<>None | Error _->true)
     | None->false) in
  let pending=List.exists (fun row->text "state" row="pending") !rows in
  let attempts month side=List.length (List.filter (fun row->text "month" row=month && text "side" row=side) !rows) in
  let send side qty limit (reading:Monthly_trend.reading) origin =
    let attempt=attempts reading.month side in
    let cid=Crypto_trend_broker.client_id ~month:reading.month ~side ~origin ~attempt in
    let request=`Assoc ["qty",`String (Exact_decimal.to_string qty);"limitPrice",`Float limit] in
    let row=`Assoc ["clientOrderId",`String cid;"side",`String side;"state",`String "pending";"month",`String reading.month;
      "sentAt",`String (Multi_paper.observed_stamp (Unix.gettimeofday ()));"request",request;
      "originEntryId",`String origin;"reading",Monthly_trend.reading_to_json reading;
      "quote",`Assoc ["time",`String quote.timestamp;"bid",`Float quote.bid;"ask",`Float quote.ask]] in
    rows:= !rows @ [row];save !rows;journal "DECISION" cid row;
    let set state extra=rows:=List.map (fun r->if text "clientOrderId" r=cid then
      List.fold_left (fun r (k,v)->replace k v r) (replace "state" (`String state) r) extra else r) !rows;save !rows in
    if not (Multi_paper.quote_fresh ~now:(Unix.gettimeofday ()) quote) then (
      set "rejected" ["brokerError",`String "Not submitted: quote expired during durable writes"];
      journal "NOT_SENT" cid `Null;note (side ^ "_not_sent") [])
    else match Crypto_trend_broker.submit ~side ~qty ~limit_price:limit ~client_order_id:cid with
      | Ok broker->validate_broker row broker;
        set (if terminal broker then "resolved" else "pending") ["broker",broker];journal "ACK" cid broker;
        note (side ^ "_routed") ["clientOrderId",`String cid]
      | Error error when List.exists (fun prefix->String.starts_with ~prefix error) ["HTTP 400:";"HTTP 403:";"HTTP 422:"] ->
        set "rejected" ["brokerError",`String error];journal "REJECTED" cid (`String error);note (side ^ "_rejected") []
      | Error error->journal "UNCERTAIN" cid (`String error);note "uncertain" ["error",`String error] in
  (match reading with
   | Error reason->note "abstain" ["reason",`String reason]
   | Ok _ when pending->note "abstain" ["reason",`String "Pending crypto trend order must reconcile first"]
   | Ok (reading,_)->
     let base=["reading",Monthly_trend.reading_to_json reading] in
     let entry_origin=match List.find_opt (fun row->text "side" row="buy" && filled row>Exact_decimal.zero) (List.rev !rows) with
       | Some row->text "clientOrderId" row | None->"" in
     match reading.decision with
     | Monthly_trend.Hold when own>=minimum->note "hold" base
     | Monthly_trend.Flat when own<minimum->note "flat" base
     | Monthly_trend.Hold ->
       if other_owner then note "abstain" (("reason",`String "BTC is held or pending under another executor; no adoption")::base)
       else if attempts reading.month "buy">=Crypto_trend_broker.max_attempts then
         note "abstain" (("reason",`String "Entry attempts for this month are exhausted")::base)
       else if not armed then note "would_buy" base
       else (match Execution_proof.Portfolio_cycle.entry_clear ~state_dir with
         | Error reason->note "abstain" (("reason",`String reason)::base)
         | Ok ()->
           let notional=unwrap (Exact_decimal.of_float Multi_paper.entry_usd) in
           let ask=unwrap (Exact_decimal.of_float quote.ask) in
           let qty=unwrap (Exact_decimal.floor_grid (unwrap (Exact_decimal.ratio notional ask)) step) in
           let limit=Paper_crypto_broker.ceil_increment (quote.ask*.(1.+.Crypto_trend_broker.buffer)) asset.tick in
           let _,_,power=unwrap (Paper_stock_broker.account ()) in
           if qty<minimum then note "abstain" (("reason",`String "Baseline notional is below the asset minimum")::base)
           else if power<Exact_decimal.to_float qty*.limit then note "abstain" (("reason",`String "Insufficient non-marginable buying power")::base)
           else send "buy" qty limit reading "")
     | Monthly_trend.Flat ->
       let sellable=unwrap (Exact_decimal.floor_grid (min own broker_qty) step) in
       if sellable<minimum then note "abstain" (("reason",`String "Owned BTC is below the asset minimum; dust retained")::base)
       else if attempts reading.month "sell">=Crypto_trend_broker.max_attempts then
         note "abstain" (("reason",`String "Exit attempts for this month are exhausted")::base)
       else if not armed then note "would_sell" base
       else send "sell" sellable (Paper_crypto_broker.floor_increment (quote.bid*.(1.-.Crypto_trend_broker.buffer)) asset.tick)
         reading entry_origin);
  let own=owned !rows in
  let held=min own broker_qty in
  (* Paper P&L: fill cash flow plus held BTC at the bid. Buy fees are already in
     the lower broker quantity; USD sell fees posted later are not included. *)
  let flow=cash_flow !rows in
  let marked=Exact_decimal.to_float held*.quote.bid in
  let result=`Assoc ["asOf",`String (Multi_paper.observed_stamp (Unix.gettimeofday ()));
    "policy",`String Monthly_trend.crypto_policy;"mode",`String (if armed then "PAPER_EXPERIMENT" else "OBSERVE");
    "ownedQuantity",`String (Exact_decimal.to_string own);"brokerQuantity",`String (Exact_decimal.to_string broker_qty);
    "pnl",`Assoc ["fillCashFlowUsd",`Float flow;"heldMarkUsd",`Float marked;"netUsd",`Float (flow+.marked);
      "excludes",`String "USD sell fees posted after the trade day"];
    "status",`List (List.rev !notes);"winProbability",`Null] in
  atomic (path "crypto-trend.json") result;
  print_endline (Yojson.Safe.to_string result)
let ()=
  let fd=Unix.openfile (path "crypto-trend.lock") [Unix.O_CREAT;Unix.O_WRONLY] 0o640 in
  Fun.protect ~finally:(fun ()->Unix.close fd) (fun ()->
    try Unix.lockf fd Unix.F_TLOCK 0;
      Execution_proof.Portfolio_cycle.run ~state_dir run
    with error->prerr_endline ("crypto trend: " ^ Printexc.to_string error);exit 1)
