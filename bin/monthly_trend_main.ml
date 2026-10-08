open Paper_market
(* Month-end ETF trend scheduler (monthly_trend_v1). Reads Alpaca daily bars,
   decides hold/flat from completed months only, and delegates every order to
   the serialized durable stock router. No network POST is implemented here. *)
let state_dir=Option.value ~default:"/home/ubuntu/jsbot-paper-state" (Sys.getenv_opt "PAPER_STATE_DIR")
let path name=Filename.concat state_dir name
let field=Paper_broker.member
let text name row=Option.value ~default:"" (Paper_broker.string (field name row))
let unwrap=function Ok value->value|Error message->failwith message
(* SOURCE: SPY/QQQ track the S&P 500 / NASDAQ series the rule was validated on.
   Other symbols are allowed via TREND_SYMBOLS but were not part of that test. *)
let symbols=match Sys.getenv_opt "TREND_SYMBOLS" with
  | Some list when String.trim list<>"" -> List.map String.trim (String.split_on_char ',' list)
  | _ -> ["SPY";"QQQ"]
let atomic filename value =
  let temporary=filename ^ ".tmp" in
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
      if text "side" row="buy" then Int64.add total qty
      else if qty>total then failwith "stock exit exceeds ownership" else Int64.sub total qty
    | None->total) Exact_decimal.zero rows
let pending ticker rows=List.exists (fun row->text "symbol" row=ticker && text "state" row="pending") rows
let latest_buy ticker rows=List.find_opt (fun row->text "symbol" row=ticker && text "side" row="buy") (List.rev rows)
let trend_owned row=Option.bind (field "analysisEvidence" row) (fun e->Paper_broker.string (field "policy" e))
  =Some Monthly_trend.policy
let router args =
  let executable=Filename.concat (Filename.dirname Sys.executable_name) "stock_paper_main.exe" in
  let sink=Unix.openfile "/dev/null" [Unix.O_WRONLY] 0 in
  Fun.protect ~finally:(fun ()->Unix.close sink) (fun ()->
    let pid=Unix.create_process executable (Array.of_list (executable::args)) Unix.stdin sink sink in
    match snd (Unix.waitpid [] pid) with Unix.WEXITED 0->true|_->false)
let iso (y,m,d)=Printf.sprintf "%04d-%02d-%02d" y m d
(* SOURCE: Alpaca market-data v2 multi-symbol daily bars, split/dividend
   adjusted. The free plan's IEX feed is not consolidated; closes can differ
   slightly from SIP closes. Pages are followed until exhausted. *)
let daily_bars ~today tickers =
  let key_id,secret=unwrap (Paper_broker.credentials ()) in
  (* 200 sessions need about ten calendar months; thirteen leave margin. *)
  let (y,m,_)=today in
  let start=iso (y-1,m,1) in
  let table=Hashtbl.create 8 in
  let rec page token count =
    if count>20 then failwith "daily bar pagination did not terminate";
    let url="https://data.alpaca.markets/v2/stocks/bars?timeframe=1Day&adjustment=all&feed=iex&limit=10000&start="
      ^ start ^ "&symbols=" ^ String.concat "%2C" tickers
      ^ (match token with Some t->"&page_token=" ^ t | None->"") in
    let doc=unwrap (Alpaca_http.get_json ~url ~key_id ~secret) in
    (match field "bars" doc with
     | Some (`Assoc rows)->List.iter (fun (symbol,bars)->match bars with
         | `List bars->List.iter (fun bar->
             let t=text "t" bar in
             match Paper_broker.float (field "c" bar) with
             | Some close when String.length t>=10 ->
               let previous=Option.value ~default:[] (Hashtbl.find_opt table symbol) in
               Hashtbl.replace table symbol ({Monthly_trend.date=String.sub t 0 10;close}::previous)
             | _->failwith "daily bar is missing a time or close") bars
         | _->()) rows
     | Some `Null | None->()
     | _->failwith "daily bars response is malformed");
    match Paper_broker.string (field "next_page_token" doc) with
    | Some t when t<>"" -> page (Some t) (count+1)
    | _->() in
  page None 0;
  fun symbol->List.rev (Option.value ~default:[] (Hashtbl.find_opt table symbol))
let run ()=
  if not (router ["--check"]) then failwith "stock reconciliation/preflight health check failed";
  let now=Unix.gettimeofday () in
  let t=Unix.gmtime now in
  let today=(t.tm_year+1900,t.tm_mon+1,t.tm_mday) in
  let armed=Array.exists ((=) "--execute") Sys.argv && Sys.getenv_opt "PAPER_ORDERS"=Some "1" &&
    Sys.getenv_opt "STOCK_PAPER_ORDERS"=Some "1" && Sys.getenv_opt "TREND_AUTO_ORDERS"=Some "1" in
  let clock=unwrap (Paper_broker.get "/v2/clock") in
  let session=Paper_broker.bool (field "is_open" clock)=Some true in
  let bars=daily_bars ~today symbols in
  let rows=ref (orders ()) and invoked=ref 0 and report=ref [] in
  let note symbol status detail=report:=`Assoc (["symbol",`String symbol;"status",`String status]@detail):: !report in
  let transmit ticker side amount cid evidence =
    let intent=path ("trend-intent-" ^ cid ^ ".json") in
    atomic intent evidence;
    let ok=router [if side="buy" then "--buy" else "--sell";ticker;"--amount";amount;
      "--client-id";cid;"--reason";"Month-end close vs 200-session average (monthly_trend_v1)";
      "--evidence-file";intent;"--execute"] in
    incr invoked;rows:=orders ();
    ok in
  List.iter (fun ticker->
    let history=bars ticker in
    match Monthly_trend.decide ~today history with
    | Error reason->note ticker "abstain" ["reason",`String reason]
    | Ok reading->
      let qty=owned ticker !rows in
      let entry=latest_buy ticker !rows in
      let base=["reading",Monthly_trend.reading_to_json reading;"ownedQuantity",`String (Exact_decimal.to_string qty)] in
      let intent side cid extra=`Assoc (["symbol",`String ticker;"side",`String side;"clientOrderId",`String cid;
        "policy",`String Monthly_trend.policy;"bars",Monthly_trend.bars_to_json history]@extra) in
      if pending ticker !rows then note ticker "abstain" (("reason",`String "Pending order must reconcile first")::base)
      else match reading.decision with
      | Monthly_trend.Hold when qty=Exact_decimal.zero ->
        let cid=Monthly_trend.client_id ~symbol:ticker ~month:reading.month ~side:"buy" ~origin:"" in
        if List.exists (fun row->text "clientOrderId" row=cid) !rows then
          note ticker "abstain" (("reason",`String "This month's entry was already attempted")::base)
        else if not (armed && session) then
          note ticker "would_buy" (("reason",`String (if armed then "Regular session closed" else "Observe mode"))::base)
        else note ticker (if transmit ticker "buy" (Exact_decimal.to_string (unwrap (Exact_decimal.of_float Multi_paper.entry_usd)))
                              cid (intent "buy" cid []) then "buy_routed" else "buy_rejected") base
      | Monthly_trend.Hold when Option.fold ~none:false ~some:trend_owned entry -> note ticker "hold" base
      | Monthly_trend.Hold -> note ticker "abstain" (("reason",`String "Owned shares belong to another policy or manual entry")::base)
      | Monthly_trend.Flat when qty=Exact_decimal.zero -> note ticker "flat" base
      | Monthly_trend.Flat ->
        (match entry with
         | Some entry when trend_owned entry ->
           let origin=text "clientOrderId" entry in
           let cid=Monthly_trend.client_id ~symbol:ticker ~month:reading.month ~side:"sell" ~origin in
           if List.exists (fun row->text "clientOrderId" row=cid) !rows then
             note ticker "abstain" (("reason",`String "This month's exit was already attempted")::base)
           else if not (armed && session) then
             note ticker "would_sell" (("reason",`String (if armed then "Regular session closed" else "Observe mode"))::base)
           else note ticker (if transmit ticker "sell" (Exact_decimal.to_string qty) cid
                                 (intent "sell" cid ["originEntryId",`String origin]) then "sell_routed" else "sell_rejected") base
         | _->note ticker "abstain" (("reason",`String "Owned shares belong to another policy or manual entry")::base))
  ) symbols;
  let result=`Assoc ["asOf",`String (Multi_paper.observed_stamp (Unix.gettimeofday ()));
    "policy",`String Monthly_trend.policy;"mode",`String (if armed then "PAPER_EXPERIMENT" else "OBSERVE");
    "sessionOpen",`Bool session;"entryUsd",`Float Multi_paper.entry_usd;
    "routerInvocations",`Int !invoked;"symbols",`List (List.rev !report);"winProbability",`Null] in
  atomic (path "monthly-trend.json") result;
  print_endline (Yojson.Safe.to_string result)
let ()=
  let fd=Unix.openfile (path "monthly-trend.lock") [Unix.O_CREAT;Unix.O_WRONLY] 0o640 in
  Fun.protect ~finally:(fun ()->Unix.close fd) (fun ()->try Unix.lockf fd Unix.F_TLOCK 0;run ()
    with error->prerr_endline ("monthly trend: " ^ Printexc.to_string error);exit 1)
