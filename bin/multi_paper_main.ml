open Paper_market

let state_dir = match Sys.getenv_opt "PAPER_STATE_DIR" with
  | Some path -> path | None -> "/home/ubuntu/jsbot-paper-state"
let path name = Filename.concat state_dir name
let ledger_path = path "multi-paper-ledger.json"
let snapshot_path = path "multi-paper.json"
let event_path = path "multi-paper-events.jsonl"

let atomic file document =
  let temporary = file ^ ".tmp" in
  (* SOURCE: private operational ledger, readable by owner and owner group. *)
  let fd = Unix.openfile temporary [Unix.O_WRONLY; Unix.O_CREAT; Unix.O_TRUNC] 0o640 in
  let output = Unix.out_channel_of_descr fd in
  Fun.protect ~finally:(fun () -> close_out_noerr output) (fun () ->
    output_string output (Yojson.Safe.to_string document ^ "\n");
    flush output; Unix.fsync fd);
  Unix.rename temporary file;
  let directory = Unix.openfile (Filename.dirname file) [Unix.O_RDONLY] 0 in
  Fun.protect ~finally:(fun () -> Unix.close directory) (fun () -> Unix.fsync directory)

let event kind (ticket : Multi_paper.ticket) extra =
  let document = `Assoc (["at",`String (Multi_paper.stamp (Unix.gettimeofday ()));
    "kind",`String kind; "symbol",`String ticket.symbol; "frame",`String ticket.frame;
    "signalBar",`String ticket.bar; "policy",`String "trend_candle_confluence_v1"] @ extra) in
  let fd = Unix.openfile event_path [Unix.O_WRONLY; Unix.O_CREAT; Unix.O_APPEND] 0o640 in
  let output = Unix.out_channel_of_descr fd in
  Fun.protect ~finally:(fun () -> close_out_noerr output) (fun () ->
    output_string output (Yojson.Safe.to_string document ^ "\n"); flush output; Unix.fsync fd)

let read_state () =
  if not (Sys.file_exists ledger_path) then Ok Multi_paper.empty
  else try Multi_paper.of_json (Yojson.Safe.from_file ledger_path)
       with _ -> Error "durable ledger cannot be read; refusing to reset ownership"

let persist state = atomic ledger_path (Multi_paper.to_json state)
let pending_fields (pending : Multi_paper.pending) = [
  "clientOrderId",`String pending.client_id; "side",`String pending.side;
  "requestedQty",`Float pending.requested_qty; "limitPrice",`Float pending.limit_price;
  "reason",`String pending.reason; "reading",pending.reading]

let run ~execute () =
  let state = ref (match read_state () with Ok state -> state | Error e -> failwith e) in
  let failures = ref [] and actions = ref [] in
  let failure symbol reason = failures := `Assoc ["symbol",`String symbol;
    "reason",`String reason] :: !failures in
  let replace ticket = state := Multi_paper.replace_ticket !state ticket; persist !state in
  let reconcile (ticket : Multi_paper.ticket) = match ticket.pending with
    | None -> ()
    | Some pending ->
      (match Paper_broker.order_by_client_id pending.client_id with
       | Error _ -> failure ticket.symbol "Pending order outcome unavailable; no resubmission"
       | Ok order -> match Multi_paper.reconcile ticket order with
         | Error e -> failure ticket.symbol e
         | Ok next ->
           if next.pending = None then (
             replace next;
             event "RECONCILED" next (["clientOrderId",`String pending.client_id;
               "side",`String pending.side; "status",Option.value ~default:`Null
                 (Paper_broker.member "status" order);
               "filledQty",Option.value ~default:`Null (Paper_broker.member "filled_qty" order);
               "filledAveragePrice",Option.value ~default:`Null
                 (Paper_broker.member "filled_avg_price" order)])) ) in
  (* SOURCE: resolve every durable pending order before new exposure decisions. *)
  List.iter reconcile (Multi_paper.active_tickets !state);
  let document = try Yojson.Safe.from_file (path "market-pipeline.json")
                 with _ -> `Null in
  let now = Unix.gettimeofday () in
  let signals = match Multi_paper.signals ~now document with
    | Ok signals -> signals | Error e -> failure "all" e; [] in
  let armed = execute && Sys.getenv_opt "MULTI_PAPER_ORDERS" = Some "1" &&
              Sys.getenv_opt "PAPER_ORDERS" = Some "1" in
  let transmit (ticket : Multi_paper.ticket) (asset : Paper_crypto_broker.asset) =
    let pending = Option.get ticket.pending in
    (* SOURCE: the ledger and decision trace are durable BEFORE the network
       POST. A timeout/unknown response leaves this pending ID unresolved. *)
    event "DECISION" ticket (pending_fields pending);
    match Paper_crypto_broker.submit ~asset ~side:pending.side ~qty:pending.requested_qty
      ~limit_price:pending.limit_price ~client_order_id:pending.client_id with
    | Error error ->
      (* SOURCE: HTTP 422 explicitly rejects an invalid Alpaca order. Every
         other transport/HTTP error remains ambiguous and keeps the pending ID. *)
      if String.starts_with ~prefix:"HTTP 422:" error then (
        let next = {ticket with pending=None; closed=(pending.side="buy")} in
        replace next; event "REJECTED" next (pending_fields pending);
        failure ticket.symbol "Broker rejected order (HTTP 422); this signal is not retried")
      else (event "UNCERTAIN" ticket (pending_fields pending);
        failure ticket.symbol "Order response uncertain; pending ID retained")
    | Ok order ->
      event "ACK" ticket ["clientOrderId",`String pending.client_id];
      (match Multi_paper.reconcile ticket order with
       | Error error -> failure ticket.symbol error
       | Ok next ->
         if next.pending = None then replace next);
      actions := `Assoc ["symbol",`String ticket.symbol; "frame",`String ticket.frame;
        "side",`String pending.side; "clientOrderId",`String pending.client_id] :: !actions in
  let account = Paper_broker.account () in
  let account_ok side =
    match account with
    | Ok ("ACTIVE",false,power) when side="sell" || power >= Multi_paper.entry_usd -> true
    | _ -> failure "all" "Account is blocked, inactive, unavailable or lacks non-marginable buying power"; false in
  (* SOURCE: broker positions/open orders and batched latest quotes are read
     once per serialized run. Fetch asset increments only for a possible order,
     avoiding broker metadata/position polling for every unchanged holding. *)
  let symbols = List.sort_uniq String.compare (List.map (fun (s:Multi_paper.signal) -> s.symbol) signals @
    List.map (fun (t:Multi_paper.ticket) -> t.symbol) (Multi_paper.active_tickets !state)) in
  let positions = Paper_crypto_broker.positions () and orders = Paper_crypto_broker.open_orders () in
  let quotes = if symbols=[] then Ok (`Assoc ["quotes",`Assoc []])
    else Paper_crypto_broker.quote_document symbols in
  let current symbol =
    match positions, orders, quotes with
    | Ok positions, Ok orders, Ok document ->
      (match Paper_crypto_broker.quantity symbol positions, Paper_crypto_broker.parse_quote symbol document with
       | _, Error error -> failure symbol error; None
       | Error error, _ -> failure symbol error; None
       | Ok _, Ok _ when Paper_crypto_broker.has_open_order symbol orders ->
         failure symbol "An existing broker order blocks this instrument"; None
       | Ok _, Ok quote when not (Multi_paper.quote_fresh ~now:(Unix.gettimeofday ()) quote) ->
         failure symbol "Latest broker quote is stale or future-dated"; None
       | Ok qty, Ok quote -> Some (qty,quote))
    | _ -> failure symbol "Position, order or quote batch read unavailable"; None in
  let preflight symbol =
    match Paper_crypto_broker.asset symbol, current symbol with
    | Ok asset, Some (qty,quote) -> Some (asset,qty,quote)
    | _ -> failure symbol "Asset preflight unavailable"; None in
  let with_quote reading (quote : Paper_crypto_broker.quote) =
    `Assoc (["triggerBid",`Float quote.bid; "triggerAsk",`Float quote.ask;
      "triggerQuoteTime",`String quote.timestamp] @ (match reading with `Assoc fields -> fields | _ -> [])) in
  let origin_reading (ticket : Multi_paper.ticket) =
    match Paper_broker.member "markets" document with
    | Some (`List rows) ->
      let row=List.find_opt (fun row -> Paper_broker.string (Paper_broker.member "symbol" row)=Some ticket.symbol &&
        Paper_broker.string (Paper_broker.member "venue" row)=Some "Alpaca crypto") rows in
      let frames=Option.bind row (Paper_broker.member "frames") in
      Option.value ~default:(`Assoc []) (Option.bind frames (Paper_broker.member ticket.frame))
    | _ -> `Assoc [] in
  (* SOURCE: exits precede entries; only this experiment's owned quantity can
     be sold. Broker fee debits may reduce inventory, but cannot increase it. *)
  List.iter (fun (original : Multi_paper.ticket) ->
    match Multi_paper.ticket_for !state original.symbol with
    | Some ticket when ticket.pending = None ->
      (match current ticket.symbol with
       | Some (qty,_) when qty > Float.next_after ticket.owned_max infinity ->
         failure ticket.symbol "Broker inventory exceeds owned quantity; external activity suspected"
       | Some (qty,_) when qty=0. ->
         replace {ticket with closed=true}; event "FLAT" ticket []
       | Some (qty,quote) ->
         (match Multi_paper.exit_reason ~now:(Unix.gettimeofday ()) ticket quote document with
          | None -> ()
          | Some _ when ticket.last_exit_quote = Some quote.timestamp -> ()
          | Some reason ->
            (match Paper_crypto_broker.asset ticket.symbol with
             | Error _ -> failure ticket.symbol "Exit asset increments unavailable"
             | Ok asset ->
            let quantity = Paper_crypto_broker.floor_increment (min qty ticket.owned_max) asset.step in
            let price = Paper_crypto_broker.floor_increment quote.bid asset.tick in
            if quantity < asset.minimum then
              failure ticket.symbol "Owned dust is below the broker's minimum order quantity"
            else if armed && account_ok "sell" &&
                Multi_paper.quote_fresh ~now:(Unix.gettimeofday ()) quote then (
              let next,ticket = Multi_paper.exit ~reading:(with_quote (origin_reading ticket) quote)
                !state ticket ~now:(Unix.gettimeofday ())
                ~qty:quantity ~price ~quote_time:quote.timestamp ~reason in
              state := next; persist next; transmit ticket asset)))
       | None -> ())
    | _ -> ()) (Multi_paper.active_tickets !state);
  List.iter (fun (signal : Multi_paper.signal) ->
    if Multi_paper.eligible !state signal then
      match preflight signal.symbol with
      | Some (_,qty,_) when qty <> 0. ->
        failure signal.symbol "Existing inventory is not owned by this experiment"
      | Some (asset,_,quote) ->
        let price = Paper_crypto_broker.ceil_increment quote.ask asset.tick in
        let qty = Paper_crypto_broker.floor_increment (Multi_paper.entry_usd /. price) asset.step in
        if signal.stop >= quote.bid then failure signal.symbol "Signal is already invalidated at the latest bid"
        else if qty < asset.minimum then failure signal.symbol "Entry is below the broker's minimum quantity"
        else if armed && account_ok "buy" &&
            Multi_paper.quote_fresh ~now:(Unix.gettimeofday ()) quote &&
            (match Multi_paper.signals ~now:(Unix.gettimeofday ()) document with
             | Ok current -> List.exists (fun (s : Multi_paper.signal) ->
                 s.symbol=signal.symbol && s.frame=signal.frame && s.bar=signal.bar) current
             | Error _ -> false) then (
          let next,ticket = Multi_paper.entry !state {signal with reading=with_quote signal.reading quote}
            ~now:(Unix.gettimeofday ()) ~qty ~price in
          state := next; persist next; transmit ticket asset)
      | None -> ()) signals;
  let result = `Assoc ["asOf",`String (Multi_paper.stamp (Unix.gettimeofday ()));
    "mode",`String (if armed then "PAPER_EXPERIMENT" else "OBSERVE");
    "policy",`String "trend_candle_confluence_v1"; "calibrated",`Bool false;
    "winProbability",`Null; "entryUsd",`Float Multi_paper.entry_usd;
    "maxOpenTickets",`Int Multi_paper.max_open_tickets;
    "eligibleLongSignals",`Int (List.length signals);
    "activeTickets",`List (List.map Multi_paper.ticket_json (Multi_paper.active_tickets !state));
    "lastActions",`List (List.rev !actions); "abstentions",`List (List.rev !failures);
    "stopHandling",`String "Local latest-bid invalidation exit; no resting broker stop";
    "legacyBtcOwner",`Bool true;
    "timeframes",`List (List.map (fun (name,_) -> `String name) Frame_analysis.frames)] in
  atomic snapshot_path result;
  print_endline (Yojson.Safe.to_string (`Assoc ["mode",`String (if armed then "PAPER_EXPERIMENT" else "OBSERVE");
    "signals",`Int (List.length signals); "ordersAcknowledged",`Int (List.length !actions);
    "abstentions",`Int (List.length !failures)]))

let () =
  let execute = Array.exists ((=) "--execute") Sys.argv in
  let fd = Unix.openfile (path "multi-paper.lock") [Unix.O_WRONLY;Unix.O_CREAT] 0o640 in
  Fun.protect ~finally:(fun () -> Unix.close fd) (fun () ->
    try Unix.lockf fd Unix.F_TLOCK 0; run ~execute ()
    with error -> prerr_endline ("multi-paper stopped: " ^ Printexc.to_string error); exit 1)
