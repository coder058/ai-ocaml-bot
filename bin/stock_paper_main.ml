open Paper_market
let state_dir=Option.value ~default:"/home/ubuntu/jsbot-paper-state" (Sys.getenv_opt "PAPER_STATE_DIR")
let path name=Filename.concat state_dir name
let field=Paper_broker.member
let string=Paper_broker.string
let get_string name row=Option.value ~default:"" (string (field name row))
let atomic file document =
  let temporary=file ^ ".tmp" in
  (* SOURCE: private operational state, same permissions as the crypto OMS. *)
  let fd=Unix.openfile temporary [Unix.O_CREAT;Unix.O_TRUNC;Unix.O_WRONLY] 0o640 in
  let output=Unix.out_channel_of_descr fd in
  Fun.protect ~finally:(fun ()->close_out_noerr output) (fun ()->
    output_string output (Yojson.Safe.to_string document ^ "\n");flush output;Unix.fsync fd);
  Unix.rename temporary file;
  let directory=Unix.openfile (Filename.dirname file) [Unix.O_RDONLY] 0 in
  Fun.protect ~finally:(fun ()->Unix.close directory) (fun ()->Unix.fsync directory)
let journal kind ticker cid reason detail =
  let row=`Assoc ["at",`String (Multi_paper.observed_stamp (Unix.gettimeofday ()));
    "kind",`String kind;"symbol",`String ticker;"clientOrderId",`String cid;
    "reason",`String reason;"detail",detail] in
  let fd=Unix.openfile (path "stock-paper-events.jsonl") [Unix.O_CREAT;Unix.O_WRONLY;Unix.O_APPEND] 0o640 in
  let output=Unix.out_channel_of_descr fd in
  Fun.protect ~finally:(fun ()->close_out_noerr output) (fun ()->
    output_string output (Yojson.Safe.to_string row ^ "\n");flush output;Unix.fsync fd)
let read_orders () =
  let file=path "stock-paper-ledger.json" in
  if not (Sys.file_exists file) then [] else
  match Yojson.Safe.from_file file with
  | `Assoc fields -> (match List.assoc_opt "orders" fields with Some (`List rows)->rows
    | _->failwith "stock ledger has no orders")
  | _->failwith "stock ledger is invalid; refusing reset"
let save orders=atomic (path "stock-paper-ledger.json") (`Assoc ["orders",`List orders])
let replace name value row=match row with `Assoc fields->`Assoc ((name,value)::List.remove_assoc name fields)
  | _->failwith "invalid stock order"
let unwrap=function Ok value->value | Error error->failwith error
let terminal order=List.mem (get_string "status" order) ["filled";"canceled";"expired";"rejected"]
let validate_broker row broker =
  if get_string "client_order_id" broker<>get_string "clientOrderId" row ||
     get_string "symbol" broker<>get_string "symbol" row ||
     get_string "side" broker<>get_string "side" row then failwith "stock broker ownership mismatch";
  let qty=unwrap (Exact_decimal.of_string (get_string "filled_qty" broker)) in
  (match field "broker" row with
   | Some previous ->
     let before=unwrap (Exact_decimal.of_string (get_string "filled_qty" previous)) in
     if qty<before then failwith "stock cumulative fills decreased"
   | None -> ());
  (match field "request" row with
   | Some request when get_string "side" row="sell" ->
     let requested=unwrap (Exact_decimal.of_string (get_string "qty" request)) in
     if qty>requested then failwith "stock sell overfill"
   | _ -> ());
  if qty>Exact_decimal.zero then (
    let price=unwrap (Exact_decimal.of_string (get_string "filled_avg_price" broker)) in
    if price=Exact_decimal.zero then failwith "filled stock order has no positive price");
  if not (List.mem (get_string "status" broker)
      ["new";"accepted";"pending_new";"partially_filled";"filled";"canceled";
       "expired";"rejected";"pending_cancel";"pending_replace";"done_for_day";
       "held";"stopped";"suspended";"calculated";"replaced"]) then
    failwith "stock order status is missing or unsupported"
let owned_quantity ticker orders =
  List.fold_left (fun total row ->
    if get_string "symbol" row<>ticker then total else
    match field "broker" row with
    | Some broker ->
      let qty=unwrap (Exact_decimal.of_string (get_string "filled_qty" broker)) in
      if get_string "side" row="buy" then
        if total > Int64.sub Int64.max_int qty then failwith "owned quantity overflow"
        else Int64.add total qty
      else if qty > total then failwith "stock exits exceed owned fills"
      else Int64.sub total qty
    | None -> total) Exact_decimal.zero orders
let argument name =
  let args=Array.to_list Sys.argv in
  let rec find=function key::value::_ when key=name->Some value | _::rest->find rest | []->None in
  find args
let run () =
  let orders=ref (read_orders ()) in
  let ids=List.map (fun row->get_string "clientOrderId" row) !orders in
  if List.length ids<>List.length (List.sort_uniq String.compare ids) then
    failwith "duplicate stock ledger IDs; refusing ownership reconstruction";
  List.iter (fun row->
    let ticker=get_string "symbol" row and cid=get_string "clientOrderId" row in
    ignore (unwrap (Paper_stock_broker.symbol ticker));
    if not (String.starts_with ~prefix:"aibotstk" cid) ||
       not (List.mem (get_string "side" row) ["buy";"sell"]) ||
       not (List.mem (get_string "state" row) ["pending";"resolved";"rejected"]) then
      failwith "invalid stock ledger ownership fields";
    (match field "request" row with
     | Some request when get_string "symbol" request=ticker &&
         get_string "client_order_id" request=cid && get_string "side" request=get_string "side" row &&
         get_string "type" request="market" && get_string "time_in_force" request="day" -> ()
     | _ -> failwith "stock durable request identity mismatch");
    match field "broker" row with Some broker->validate_broker row broker | None->()) !orders;
  orders := List.map (fun row ->
    if get_string "state" row<>"pending" then row else
    let cid=get_string "clientOrderId" row in
    match Paper_broker.order_by_client_id cid with
    | Error error -> journal "LOOKUP_UNCERTAIN" (get_string "symbol" row) cid "pending order retained" (`String error);row
    | Ok broker ->
      validate_broker row broker;
      replace "state" (`String (if terminal broker then "resolved" else "pending"))
        (replace "broker" broker row)) !orders;
  save !orders;
  let clock=unwrap (Paper_broker.get "/v2/clock") in
  let account_status,account_blocked,_=unwrap (Paper_stock_broker.account ()) in
  let account_ready=account_status="ACTIVE" && not account_blocked in
  let session=Paper_broker.bool (field "is_open" clock)=Some true in
  let requested=match argument "--buy",argument "--sell" with
    | Some ticker,None->Some (ticker,"buy") | None,Some ticker->Some (ticker,"sell")
    | None,None->None | _->failwith "choose one order side" in
  (match requested with None->() | Some (ticker,side)->
    let asset=unwrap (Paper_stock_broker.asset ticker) in
    let cid=match argument "--client-id" with Some id->id | None->failwith "explicit idempotent client ID required" in
    if List.exists (fun row->get_string "clientOrderId" row=cid) !orders then
      journal "DUPLICATE_REQUEST" ticker cid "existing owned request; no resubmission" `Null
    else (
      let amount=match argument "--amount" with Some text->text | None->failwith "explicit dollar amount or sell quantity required" in
      let body=unwrap (Paper_stock_broker.body ~asset ~side ~amount ~client_order_id:cid) in
      let positions=unwrap (Paper_stock_broker.positions ()) in
      let current=unwrap (Paper_stock_broker.quantity ticker positions) in
      let own=owned_quantity ticker !orders in
      let pending=List.exists (fun row->get_string "symbol" row=ticker && get_string "state" row="pending") !orders in
      let open_orders=unwrap (Paper_crypto_broker.open_orders ()) in
      if pending || List.exists (fun row->get_string "symbol" row=ticker) open_orders then failwith "existing order blocks ticker";
      if current<>own then failwith "stock broker inventory differs from owned fills";
      let exact=unwrap (Exact_decimal.of_string amount) in
      if side="buy" && current<>Exact_decimal.zero then failwith "one position per ticker; no new entry";
      if side="sell" && (exact>own || own=Exact_decimal.zero) then failwith "sell exceeds owned quantity";
      let status,blocked,power=unwrap (Paper_stock_broker.account ()) in
      if status<>"ACTIVE" || blocked then failwith "paper account is not active";
      if side="buy" && power<Exact_decimal.to_float exact then failwith "insufficient non-marginable buying power";
      if not session then failwith "regular stock session is closed; no queued order";
      let evidence=match argument "--evidence-file" with
        | None->`Null
        | Some file ->
          let evidence=Yojson.Safe.from_file file in
          if get_string "symbol" evidence<>ticker || get_string "clientOrderId" evidence<>cid ||
             get_string "side" evidence<>side || get_string "policy" evidence<>"trend_candle_confluence_v1" then
            failwith "automatic stock intent identity mismatch";
          if Sys.getenv_opt "STOCK_AUTO_ORDERS"<>Some "1" then failwith "automatic stock paper gate is not armed";
          if side="buy" then (
            if Sys.getenv_opt "STOCK_AUTO_NEW_ENTRIES"<>Some "1" then failwith "automatic stock new entries are paused";
            if exact<>unwrap (Exact_decimal.of_float Multi_paper.entry_usd) then failwith "automatic stock entry must use the user baseline";
            let document=Option.value ~default:`Null (field "analysis" evidence) in
            let signals=unwrap (Stock_policy.signals ~now:(Unix.gettimeofday ()) document) in
            if not (List.exists (fun (s:Stock_policy.signal)->s.symbol=ticker && Stock_policy.entry_id s=cid &&
                get_string "frame" evidence=s.frame && get_string "signalBar" evidence=s.bar &&
                Paper_broker.float (field "invalidationLevel" evidence)=Some s.stop && field "reading" evidence=Some s.reading) signals) then
              failwith "automatic stock signal is no longer current")
          else (
            let origin=get_string "originEntryId" evidence in
            let managed=List.find_opt (fun row->get_string "symbol" row=ticker && get_string "side" row="buy") (List.rev !orders) in
            match managed with
            | Some row when get_string "clientOrderId" row=origin && field "analysisEvidence" row<>None->()
            | _->failwith "automatic exit has no owned managed entry");
          let quote_doc=unwrap (Paper_stock_broker.quotes [ticker]) in
          let quote=unwrap (Stock_policy.quote ~now:(Unix.gettimeofday ()) ~symbol:ticker quote_doc) in
          if side="buy" && Option.value ~default:infinity (Paper_broker.float (field "invalidationLevel" evidence))>=quote.bid then
            failwith "automatic stock signal is already invalidated at the latest IEX bid";
          if side="sell" then (
            let origin=List.find (fun row->get_string "clientOrderId" row=get_string "originEntryId" evidence) !orders in
            let origin_evidence=Option.get (field "analysisEvidence" origin) in
            let stop=match Paper_broker.float (field "invalidationLevel" origin_evidence) with
              | Some stop when Float.is_finite stop && stop>0.->stop|_->failwith "managed entry stop invalid" in
            let document=try Yojson.Safe.from_file (path "market-pipeline.json") with _->`Null in
            match Stock_policy.exit_reason ~now:(Unix.gettimeofday ()) ~stop
                ~frame:(get_string "frame" origin_evidence) ~symbol:ticker quote document with
            | Some _->()
            | None->failwith "automatic exit trigger no longer holds at the router boundary");
          (* SOURCE: re-fetch at the serialized router boundary; a scheduler's
             earlier quote does not prove that the executable quote is fresh. *)
          replace "preflight" (`Assoc ["regularSessionOpen",`Bool session;
            "accountReady",`Bool true;"buyingPowerChecked",`Bool (side="buy");
            "buyingPowerSufficient",(if side="buy" then `Bool true else `Null);
            "brokerQuantity",`String (Exact_decimal.to_string current);
            "ownedQuantity",`String (Exact_decimal.to_string own);"existingOrders",`Bool false;
            "quoteTime",`String quote.timestamp;"bid",`Float quote.bid;"ask",`Float quote.ask]) evidence in
      if not (Array.exists ((=) "--execute") Sys.argv) then
        print_endline (Yojson.Safe.to_string (`Assoc ["dryRun",`Bool true;"request",Yojson.Safe.from_string body]))
      else (
        if Sys.getenv_opt "PAPER_ORDERS"<>Some "1" || Sys.getenv_opt "STOCK_PAPER_ORDERS"<>Some "1" then failwith "stock paper gates are not armed";
        let reason=Option.value ~default:"explicit paper execution request; no automatic strategy" (argument "--reason") in
        let row=`Assoc (["symbol",`String ticker;"side",`String side;"clientOrderId",`String cid;
          "state",`String "pending";"sentAt",`String (Multi_paper.observed_stamp (Unix.gettimeofday ()));
          "reason",`String reason;"request",Yojson.Safe.from_string body] @
          if evidence=`Null then [] else ["analysisEvidence",evidence]) in
        orders:= !orders @ [row];save !orders;
        journal "DECISION" ticker cid reason (if evidence=`Null then Yojson.Safe.from_string body else evidence);
        (* SOURCE: durable intent/event fsync can outlive the quote or closed
           bar used by preflight. Recheck immediately before network submission. *)
        let boundary_now=Unix.gettimeofday () in
        let boundary_valid=if evidence=`Null then true else
          let quote_time=Option.bind (field "preflight" evidence) (field "quoteTime") in
          let quote_at=Option.bind (Paper_broker.string quote_time) Stock_policy.timestamp in
          let quote_fresh=match quote_at with Some at ->
            boundary_now>=at && boundary_now-.at<=Multi_paper.max_quote_age_seconds | None->false in
          let signal_current=side="sell" || match Stock_policy.signals ~now:boundary_now
            (Option.value ~default:`Null (field "analysis" evidence)) with
            | Ok signals->List.exists (fun (s:Stock_policy.signal)->Stock_policy.entry_id s=cid) signals
            | Error _->false in
          quote_fresh && signal_current in
        if not boundary_valid then (
          let rejected=replace "state" (`String "rejected")
            (replace "brokerError" (`String "Not submitted: quote or candidate expired during durable writes") row) in
          orders:=List.map (fun entry->if get_string "clientOrderId" entry=cid then rejected else entry) !orders;
          save !orders;
          journal "NOT_SENT" ticker cid "quote or candidate expired during durable writes" evidence)
        else match Paper_stock_broker.submit ~asset ~side ~amount ~client_order_id:cid with
        | Ok broker ->
          validate_broker row broker;
          let updated=replace "state" (`String (if terminal broker then "resolved" else "pending")) (replace "broker" broker row) in
          orders:=List.map (fun row->if get_string "clientOrderId" row=cid then updated else row) !orders;
          save !orders;journal "ACK" ticker cid reason broker
        | Error error ->
          (* SOURCE: explicit request rejection statuses; other errors retain the durable ID. *)
          if List.exists (fun prefix->String.starts_with ~prefix error) ["HTTP 400:";"HTTP 403:";"HTTP 422:"] then (
            let rejected=replace "state" (`String "rejected") (replace "brokerError" (`String error) row) in
            orders:=List.map (fun row->if get_string "clientOrderId" row=cid then rejected else row) !orders;save !orders;
            journal "REJECTED" ticker cid reason (`String error))
          else journal "UNCERTAIN" ticker cid reason (`String error))));
  let symbols=match argument "--symbols" with Some text->String.split_on_char ',' text
    | None->["DIA";"QQQ";"SPY";"XLE";"XOP";"TSLA";"NVDA";"MSFT";"AMZN";"GOOGL";"META";"AMD"] in
  (* SOURCE: initial stock/ETF universe from the user's requested markets. *)
  let quotes=match Paper_stock_broker.quotes symbols with Ok result->result | Error error->`Assoc ["error",`String error] in
  let result=`Assoc ["asOf",`String (Multi_paper.observed_stamp (Unix.gettimeofday ()));
    "provider",`String "Alpaca paper";"product",`String "US stocks / ETF";
    "connected",`Bool true;"sessionOpen",`Bool session;"nextOpen",Option.value ~default:`Null (field "next_open" clock);
    "accountReady",`Bool account_ready;
    "automaticStrategy",`Bool false;"executionGateArmed",`Bool (Sys.getenv_opt "STOCK_PAPER_ORDERS"=Some "1");
    "canSubmitNow",`Bool (session && account_ready && Sys.getenv_opt "STOCK_PAPER_ORDERS"=Some "1" &&
      Sys.getenv_opt "PAPER_ORDERS"=Some "1");"feed",`String "iex";"quotes",quotes;"ownedOrders",`List !orders] in
  atomic (path "stock-connection.json") result;
  print_endline (Yojson.Safe.to_string (`Assoc ["connected",`Bool true;"sessionOpen",`Bool session;"orders",`Int (List.length !orders)]))
let () =
  let fd=Unix.openfile (path "stock-paper.lock") [Unix.O_WRONLY;Unix.O_CREAT] 0o640 in
  Fun.protect ~finally:(fun ()->Unix.close fd) (fun ()->
    try Unix.lockf fd Unix.F_TLOCK 0;run ()
    with error->prerr_endline ("stock paper router: " ^ Printexc.to_string error);exit 1)
