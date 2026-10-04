open Paper_market
open Paper_crypto

(* # SOURCE: synthetic values exercise branches; they are not market data. *)

let check ok msg = if not ok then failwith msg

let quote timestamp bid ask =
  Paper_crypto.{ bid; ask; bid_size = 1.; ask_size = 1.; timestamp }

let () =
  let old = quote "2026-09-27T01:00:00Z" 100. 101. in
  let up = quote "2026-09-27T01:00:01Z" 102. 103. in
  let down = quote "2026-09-27T01:00:02Z" 98. 99. in
  (* # SOURCE: synthetic quote pairs; expected cross gaps are 10,000/101 and
     10,000/99 basis points. 1e-9 is only a Float unit-test tolerance. *)
  (match Paper_crypto.quote_cross_evidence ~previous:old ~current:up with
   | Some ("up", move) ->
     check (Float.abs (move -. (10_000. /. 101.)) < 1e-9) "up cross margin"
   | _ -> failwith "up cross evidence");
  (match Paper_crypto.quote_cross_evidence ~previous:old ~current:down with
   | Some ("down", move) ->
     check (Float.abs (move -. (10_000. /. 99.)) < 1e-9) "down cross margin"
   | _ -> failwith "down cross evidence");
  let inside = quote "2026-09-27T01:00:03Z" 100.5 101.5 in
  check (Paper_crypto.quote_cross_evidence ~previous:old ~current:inside = None)
    "no-cross evidence";
  check (Paper_crypto.decide ~previous:old ~current:up ~position_qty:0.
           ~has_open_order:false = Buy) "buy on crossed quote";
  check (Paper_crypto.decide ~previous:old ~current:down ~position_qty:0.01
           ~has_open_order:false = Sell) "sell on crossed quote";
  check (Paper_crypto.decide ~previous:old ~current:up ~position_qty:0.
           ~has_open_order:true = Hold "broker has an open order") "open-order guard";
  check (Paper_crypto.decide ~previous:up ~current:old ~position_qty:0.
           ~has_open_order:false = Hold "market quote has not advanced") "stale guard";
  (* # SOURCE: synthetic receipt times exercise the historical 30-second
     sample cadence; these are not observed market latencies. *)
  check (not (Paper_crypto.sample_due ~reference_received_ns:0
           ~current_received_ns:29_999_999_999)) "do not sample early";
  check (Paper_crypto.sample_due ~reference_received_ns:0
           ~current_received_ns:30_000_000_000) "sample at prior cadence";
  check (not (Paper_crypto.sample_due ~reference_received_ns:30_000_000_000
           ~current_received_ns:0)) "reject backward receipt time";
  (* # SOURCE: user-specified tier sizes; the limit-price calculation may not
     exceed the selected paper order notional after quantity rounding. *)
  check (Paper_crypto.order_notional Experimental_baseline = 100.) "base tier";
  check (Paper_crypto.order_notional Calibrated_lower = 50.) "lower tier";
  check (Paper_crypto.order_notional Calibrated_higher = 500.) "higher tier";
  let base_qty = Paper_crypto.buy_qty ~ask:84_000. ~notional:100. in
  check (Option.is_some base_qty) "valid qty";
  check (Option.get base_qty *. 84_000. <= 100.) "order notional cap";
  check (Paper_crypto.buy_qty ~ask:0. ~notional:100. = None) "invalid ask";
  check (Paper_crypto.buy_qty ~ask:84_000. ~notional:0. = None) "invalid target";
  (* # SOURCE: $10 Alpaca USD crypto minimum; synthetic values test boundary. *)
  check (Paper_crypto.is_dust ~price:100. ~qty:0.099) "subminimum dust";
  check (not (Paper_crypto.is_dust ~price:100. ~qty:0.1)) "minimum is tradable";
  let payload = Yojson.Safe.from_string
    {|{"quotes":{"BTC/USD":{"bp":100.0,"ap":101.0,"bs":1.0,"as":2.0,"t":"2026-09-27T01:00:00Z"}}}|} in
  check (Result.is_ok (Paper_crypto.parse_quote payload)) "quote parse";
  let quote_event = Yojson.Safe.from_string
    {|{"T":"q","S":"BTC/USD","bp":100.0,"ap":101.0,"bs":1.0,"as":2.0,"t":"2026-09-27T01:00:00Z"}|} in
  check (Result.is_ok (Paper_crypto.parse_quote_event quote_event)) "live quote event parse";
  let wrong_symbol = Yojson.Safe.from_string
    {|{"T":"q","S":"ETH/USD","bp":100.0,"ap":101.0,"bs":1.0,"as":2.0,"t":"2026-09-27T01:00:00Z"}|} in
  check (Result.is_error (Paper_crypto.parse_quote_event wrong_symbol)) "live quote event symbol guard";
  let body, code = Alpaca_http.split_status "{\"ok\":true}\n__HTTP_STATUS__:200\n" in
  check (code = 200 && body = "{\"ok\":true}") "HTTP status with trailing newline";
  print_endline "paper crypto policy checks passed"
