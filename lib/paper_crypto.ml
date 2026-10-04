(* A deliberately small live-paper policy. The direction rule is a diagnostic
   heuristic, not a calibrated claim of edge. All prices come from Alpaca's
   current crypto quote endpoint; historical/synthetic values never reach it. *)

type quote = {
  bid : float;
  ask : float;
  bid_size : float;
  ask_size : float;
  timestamp : string;
}

type action = Buy | Sell | Hold of string

let member name = function
  | `Assoc fields -> List.assoc_opt name fields
  | _ -> None

let number = function
  | Some (`Float x) -> Some x
  | Some (`Int x) -> Some (float_of_int x)
  | Some (`String x) -> (try Some (float_of_string x) with _ -> None)
  | _ -> None

let positive_finite x = Float.is_finite x && x > 0.

let parse_quote j =
  let q = Option.bind (member "quotes" j) (member "BTC/USD") in
  match q with
  | None -> Error "BTC/USD quote absent"
  | Some q ->
    (match number (member "bp" q), number (member "ap" q),
           number (member "bs" q), number (member "as" q), member "t" q with
     | Some bid, Some ask, Some bid_size, Some ask_size, Some (`String timestamp)
       when positive_finite bid && positive_finite ask && bid < ask
            && positive_finite bid_size && positive_finite ask_size
            && timestamp <> "" ->
       Ok { bid; ask; bid_size; ask_size; timestamp }
     | _ -> Error "invalid BTC/USD quote fields")

let parse_quote_event event =
  match member "T" event, member "S" event with
  | Some (`String "q"), Some (`String "BTC/USD") ->
    (match number (member "bp" event), number (member "ap" event),
           number (member "bs" event), number (member "as" event),
           member "t" event with
     | Some bid, Some ask, Some bid_size, Some ask_size, Some (`String timestamp)
       when positive_finite bid && positive_finite ask && bid < ask
            && positive_finite bid_size && positive_finite ask_size
            && timestamp <> "" ->
       Ok { bid; ask; bid_size; ask_size; timestamp }
     | _ -> Error "invalid live BTC/USD quote event fields")
  | _ -> Error "unexpected live quote event symbol or type"

let quote_url =
  "https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes?symbols=BTC%2FUSD"

let fetch_quote () =
  match Alpaca_http.get_public_json ~url:quote_url with
  | Error e -> Error e
  | Ok j -> parse_quote j

let midpoint q = (q.bid +. q.ask) /. 2.
let spread_bps q = (q.ask -. q.bid) /. midpoint q *. 10_000.
(* # SOURCE: one basis point is 1/10,000, by definition. *)

let quote_cross_evidence ~previous ~current =
  (* # SOURCE: quote_cross_30s_v1 triggers on current bid > prior ask (up)
     or current ask < prior bid (down); express the observed gap in basis points. *)
  if current.bid > previous.ask then
    Some ("up", ((current.bid /. previous.ask) -. 1.) *. 10_000.)
  else if current.ask < previous.bid then
    Some ("down", ((previous.bid /. current.ask) -. 1.) *. 10_000.)
  else None

(* # SOURCE: the earlier paper REST loop sampled quotes every 30 seconds;
   reuse that cadence on the WebSocket, without treating it as a calibrated edge. *)
let sample_interval_ns = 30_000_000_000

let sample_due ~reference_received_ns ~current_received_ns =
  current_received_ns >= reference_received_ns
  && current_received_ns - reference_received_ns >= sample_interval_ns

let is_dust ~price ~qty =
  (* # SOURCE: Alpaca documents a $10 minimum for USD crypto-pair orders. *)
  positive_finite price && Float.is_finite qty && qty >= 0.
  && qty *. price < 10.

let decide ~previous ~current ~position_qty ~has_open_order =
  if has_open_order then Hold "broker has an open order"
  else if current.timestamp <= previous.timestamp then Hold "market quote has not advanced"
  else if not (Float.is_finite position_qty) || position_qty < 0. then
    Hold "invalid broker position"
  else if position_qty = 0. && current.bid > previous.ask then Buy
  else if position_qty > 0. && current.ask < previous.bid then Sell
  else Hold "no cross-spread price move"

type sizing_tier = Experimental_baseline | Calibrated_lower | Calibrated_higher

let order_notional = function
  (* # SOURCE: user's 27 September 2026 instruction: $100 ordinary paper bet. *)
  | Experimental_baseline -> 100.
  (* # SOURCE: user's 27 September 2026 instruction: $50 lower-probability bet.
     No signal is assigned this tier until probability calibration exists. *)
  | Calibrated_lower -> 50.
  (* # SOURCE: user's 27 September 2026 instruction: $500 higher-probability bet.
     No signal is assigned this tier until probability calibration exists. *)
  | Calibrated_higher -> 500.

let max_position_notional = order_notional Calibrated_higher

let buy_qty ~ask ~notional =
  (* # SOURCE: Alpaca crypto documentation allows up to 9 decimal places. *)
  let precision = 1_000_000_000. in
  if not (positive_finite ask && positive_finite notional) then None
  else
    let qty = floor (notional /. ask *. precision) /. precision in
    if qty *. ask >= 10. then Some qty else None
    (* # SOURCE: Alpaca crypto USD-pair minimum notional is $10. *)
