(* Small durable paper OMS model. Pure decisions/reconciliation can be tested
   without credentials, a broker connection or invented performance results. *)

type pending = {
  client_id : string; side : string; requested_qty : float; quantity_text : string option; limit_price : float;
  sent_at : string; reason : string; reading : Yojson.Safe.t;
}
type ticket = {
  symbol : string; frame : string; bar : string; entry_id : string;
  stop : float; owned_max : float; entry_price : float option;
  entry_filled : float; exit_filled : float; pending : pending option;
  closed : bool; last_exit_quote : string option;
}
type state = { tickets : ticket list; seen : (string * string) list }
type signal = { symbol : string; frame : string; bar : string;
                stop : float; reading : Yojson.Safe.t }
let empty = { tickets = []; seen = [] }
let field = Paper_broker.member
let string = Paper_broker.string
let number = Paper_broker.float
let frame_minutes name = List.assoc_opt name Frame_analysis.frames

(* SOURCE: the user's ordinary entry size. No confidence tier is calibrated. *)
let entry_usd = 100.
(* GUESS: # UNCALIBRATED GUESS — start the new paper experiment at ten open
   tickets ($1,000 entry notional); this is an operational experiment limit,
   not an optimized allocation. The separate legacy BTC cap remains $500. *)
let max_open_tickets = 10
(* GUESS: # UNCALIBRATED GUESS — two minute scans tolerate one missed scan;
   quote freshness is checked separately at the order boundary. *)
let max_snapshot_age_seconds = 120.
(* GUESS: # UNCALIBRATED GUESS — reuse the legacy orderer's five-second quote
   guard. Measure actual feed/REST delay before changing this operational gate. *)
let max_quote_age_seconds = 5.

let time_of_minute value = Option.map (fun minute -> float_of_int minute *. 60.)
  (Technical.parse_utc_minute value)
let stamp now =
  (* SOURCE: Unix.tm_year is years since 1900 and tm_mon is zero based. *)
  let t = Unix.gmtime now in Printf.sprintf "%04d-%02d-%02dT%02d:%02d:%02dZ"
    (t.tm_year + 1900) (t.tm_mon + 1) t.tm_mday t.tm_hour t.tm_min t.tm_sec
let key (signal : signal) = signal.symbol ^ "|" ^ signal.frame
let client_id parts = "jsbotmtf" ^ Digest.to_hex (Digest.string (String.concat "|" parts))
(* SOURCE: MD5 here only gives a deterministic compact order identifier; it
   does not authenticate requests, hide secrets or secure a wallet. *)

let active_tickets state = List.filter (fun (ticket : ticket) -> not ticket.closed) state.tickets
let ticket_for state symbol = List.find_opt (fun (ticket : ticket) -> ticket.symbol = symbol &&
  not ticket.closed) state.tickets
let replace_ticket state (ticket : ticket) =
  {state with tickets = ticket :: List.filter (fun (prior : ticket) -> prior.symbol <> ticket.symbol) state.tickets}

let quote_fresh ~now (quote : Paper_crypto_broker.quote) =
  let age = now -. (float_of_int quote.minute *. 60. +. quote.seconds) in
  age >= 0. && age <= max_quote_age_seconds

let signals ~now document =
  match string (field "asOf" document), field "markets" document,
        string (field "policy" document), field "orderAuthority" document with
  | Some as_of, Some (`List markets), Some "trend_candle_confluence_v1", Some (`Bool false) ->
    (match time_of_minute as_of with
     | Some timestamp when now >= timestamp && now -. timestamp <= max_snapshot_age_seconds ->
       let read_market market =
         match string (field "venue" market), string (field "symbol" market),
               field "frames" market with
         | Some "Alpaca crypto", Some symbol, Some readings ->
           (match Paper_crypto_broker.canonical symbol with
            | Error _ -> []
            | Ok "BTC/USD" -> [] (* SOURCE: legacy orderer retains exclusive BTC ownership. *)
            | Ok symbol when not (Paper_crypto_broker.allowed_entry symbol) -> []
            | Ok symbol -> List.filter_map (fun (frame, minutes) ->
                match field frame readings with
                | Some reading ->
                  (match string (field "status" reading), string (field "candidate" reading),
                         string (field "lastBarStart" reading),
                         number (field "invalidationLevel" reading), number (field "close" reading),
                         field "orderAuthority" reading, field "winProbability" reading with
                   | Some "candidate", Some "long", Some bar, Some stop, Some close,
                       Some (`Bool false), Some `Null when
                         Float.is_finite stop && Float.is_finite close && stop > 0. && stop < close ->
                     (match Technical.parse_utc_minute bar with
                      | Some minute when minute mod minutes = 0 &&
                          minute = int_of_float (now /. 60.) / minutes * minutes - minutes ->
                        Some {symbol; frame; bar; stop; reading}
                      | _ -> None)
                   | _ -> None)
                | None -> None) Frame_analysis.frames)
         | _ -> [] in
       Ok (List.concat_map read_market markets)
     | _ -> Error "analysis snapshot is stale or future-dated")
  | _ -> Error "analysis snapshot policy/schema is not the frozen read-only source"

let eligible state (signal : signal) =
  ticket_for state signal.symbol = None &&
  List.length (active_tickets state) < max_open_tickets &&
  List.assoc_opt (key signal) state.seen <> Some signal.bar

let entry ?quantity_text state (signal : signal) ~now ~qty ~price =
  let id = client_id [signal.symbol; signal.frame; signal.bar; "entry";
                      "trend_candle_confluence_v1"] in
  let pending = {client_id=id; side="buy"; requested_qty=qty; quantity_text; limit_price=price;
    sent_at=stamp now; reason="Rising EMA20/EMA50 trend and bullish candle shape on a closed bar";
    reading=signal.reading} in
  let ticket = {symbol=signal.symbol; frame=signal.frame; bar=signal.bar; entry_id=id;
    stop=signal.stop; owned_max=0.; entry_price=None; entry_filled=0.; exit_filled=0.;
    pending=Some pending; closed=false; last_exit_quote=None} in
  let state = replace_ticket state ticket in
  {state with seen = (key signal,signal.bar) :: List.remove_assoc (key signal) state.seen}, ticket

let exit_reason ~now (ticket : ticket) quote document =
  if quote.Paper_crypto_broker.bid <= ticket.stop then
    Some "Latest bid reached the entry candle low (local invalidation exit)"
  else match Option.bind (string (field "asOf" document)) time_of_minute,
             field "markets" document with
    | Some as_of, Some (`List markets) when now >= as_of &&
        now -. as_of <= max_snapshot_age_seconds ->
      let market = List.find_opt (fun market ->
        string (field "venue" market) = Some "Alpaca crypto" &&
        string (field "symbol" market) = Some ticket.symbol) markets in
      let frames = Option.bind market (field "frames") in
      let reading = Option.bind frames (field ticket.frame) in
      (match reading with
       | Some reading when string (field "trend" reading) = Some "falling" &&
           List.mem (string (field "status" reading)) [Some "ready"; Some "candidate"] ->
         (* GUESS: # UNCALIBRATED GUESS — exit when EMA trend turns falling on
            the origin frame. No target/holding period or stop distance is fitted. *)
         Some "EMA20/EMA50 trend turned falling on the position's origin frame"
       | _ -> None)
    | _ -> None

let exit ?quantity_text ?(reading=`Assoc []) state (ticket : ticket) ~now ~qty ~price ~quote_time ~reason =
  let pending = {client_id=client_id [ticket.entry_id; "exit"; quote_time]; side="sell";
    requested_qty=qty; quantity_text; limit_price=price; sent_at=stamp now; reason;
    reading=`Assoc (["invalidationLevel",`Float ticket.stop; "originFrame",`String ticket.frame] @
      (match reading with `Assoc fields -> List.remove_assoc "invalidationLevel" fields | _ -> []))} in
  let ticket = {ticket with pending=Some pending; last_exit_quote=Some quote_time} in
  replace_ticket state ticket, ticket

let final_status = function "filled" | "canceled" | "expired" | "rejected" -> true | _ -> false
let reconcile (ticket : ticket) order = match ticket.pending with
  | None -> Error "ticket has no pending order"
  | Some pending ->
    match string (field "client_order_id" order), string (field "symbol" order),
          string (field "side" order), string (field "status" order),
          number (field "filled_qty" order), number (field "filled_avg_price" order) with
    | Some id, Some symbol, Some side, Some status, Some filled, price when
        id = pending.client_id && Paper_crypto_broker.same_symbol symbol ticket.symbol &&
        side = pending.side && Float.is_finite filled && filled >= 0. &&
        filled <= pending.requested_qty &&
        (filled = 0. || match price with Some p -> Float.is_finite p && p > 0. | _ -> false) ->
      if not (final_status status) then Ok ticket
      else if side = "buy" then Ok {ticket with pending=None; owned_max=filled;
        entry_filled=filled; entry_price=price; closed=filled=0.}
      else if filled > ticket.owned_max then Error "exit filled more than owned quantity"
      else let remaining = ticket.owned_max -. filled in
        Ok {ticket with pending=None; owned_max=remaining;
          exit_filled=ticket.exit_filled +. filled; closed=remaining=0.}
    | _ -> Error "broker result cannot be matched to the durable pending order"

let pending_json p = `Assoc ["clientOrderId",`String p.client_id; "side",`String p.side;
  "quantityText",(match p.quantity_text with None -> `Null | Some text -> `String text);
  "requestedQty",`Float p.requested_qty; "limitPrice",`Float p.limit_price;
  "sentAt",`String p.sent_at; "reason",`String p.reason; "reading",p.reading]
let ticket_json (t : ticket) = `Assoc ["symbol",`String t.symbol; "frame",`String t.frame;
  "bar",`String t.bar; "entryClientOrderId",`String t.entry_id;
  "invalidationLevel",`Float t.stop; "ownedMaximumQty",`Float t.owned_max;
  "entryAveragePrice",(match t.entry_price with None -> `Null | Some p -> `Float p);
  "entryFilledQty",`Float t.entry_filled; "exitFilledQty",`Float t.exit_filled;
  "closed",`Bool t.closed;
  "lastExitQuote",(match t.last_exit_quote with None -> `Null | Some s -> `String s);
  "pending",(match t.pending with None -> `Null | Some p -> pending_json p)]
let to_json state = `Assoc ["version",`Int 1;
  (* SOURCE: schema version one is this durable ledger's initial format. *)
  "tickets",`List (List.map ticket_json state.tickets);
  "seen",`Assoc (List.map (fun (key,bar) -> key,`String bar) state.seen)]

let of_json document =
  let required_string name row = match string (field name row) with
    | Some value -> value | None -> failwith ("missing " ^ name) in
  let required_number name row = match number (field name row) with
    | Some value when Float.is_finite value -> value | _ -> failwith ("invalid " ^ name) in
  let decode row =
    let pending = match field "pending" row with
      | Some `Null -> None
      | Some p -> Some {client_id=required_string "clientOrderId" p;
          side=required_string "side" p; requested_qty=required_number "requestedQty" p;
          quantity_text=string (field "quantityText" p);
          limit_price=required_number "limitPrice" p; sent_at=required_string "sentAt" p;
          reason=required_string "reason" p; reading=Option.get (field "reading" p)}
      | _ -> failwith "pending field absent" in
    let t = {symbol=required_string "symbol" row; frame=required_string "frame" row;
      bar=required_string "bar" row; entry_id=required_string "entryClientOrderId" row;
      stop=required_number "invalidationLevel" row; owned_max=required_number "ownedMaximumQty" row;
      entry_price=number (field "entryAveragePrice" row);
      entry_filled=required_number "entryFilledQty" row; exit_filled=required_number "exitFilledQty" row;
      closed=(match field "closed" row with Some (`Bool value) -> value | _ -> failwith "closed absent");
      last_exit_quote=string (field "lastExitQuote" row); pending} in
    if Paper_crypto_broker.canonical t.symbol <> Ok t.symbol || t.symbol = "BTC/USD" ||
       frame_minutes t.frame = None || t.stop <= 0. || t.owned_max < 0. ||
       t.entry_filled < 0. || t.exit_filled < 0. ||
       not (String.starts_with ~prefix:"jsbotmtf" t.entry_id) then failwith "invalid ticket";
    (match t.pending with
     | Some p when not (List.mem p.side ["buy";"sell"]) || p.requested_qty <= 0. ||
         p.limit_price <= 0. || not (String.starts_with ~prefix:"jsbotmtf" p.client_id) ||
         (p.side="sell" && p.requested_qty > t.owned_max) -> failwith "invalid pending order"
     | _ -> ());
    (match t.pending with
     | Some p -> (match p.quantity_text with
       | None -> () (* SOURCE: older durable ledgers predate exact quantity text. *)
       | Some text -> (match Exact_decimal.of_string text with
         | Ok value when value>Exact_decimal.zero && Exact_decimal.to_float value=p.requested_qty -> ()
         | _ -> failwith "pending decimal text differs from requested owned quantity"))
     | None -> ());
    t in
  try match field "version" document, field "tickets" document, field "seen" document with
    | Some (`Int 1), Some (`List rows), Some (`Assoc seen) ->
      let tickets = List.map decode rows in
      let symbols = List.map (fun (t : ticket) -> t.symbol) tickets in
      if List.length symbols <> List.length (List.sort_uniq String.compare symbols) then
        Error "duplicate owned symbols in ledger"
      else Ok {tickets; seen=List.map (fun (key, value) -> match value with
        | `String bar -> key,bar | _ -> failwith "invalid seen bar") seen}
    | _ -> Error "durable paper ledger schema mismatch"
  with _ -> Error "durable paper ledger contains invalid fields"
