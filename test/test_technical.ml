open Paper_market

(* SOURCE: all prices and times here are synthetic test fixtures. *)
let check condition message = if not condition then failwith message

let event minute open_price high low close =
  `Assoc [
    "T", `String "b"; "S", `String "BTC/USD";
    "t", `String (Printf.sprintf "2026-09-27T12:%02d:00Z" minute);
    "o", `Float open_price; "h", `Float high;
    "l", `Float low; "c", `Float close; "v", `Float 1.;
  ]

let parse minute open_price high low close =
  match Technical.parse_bar (event minute open_price high low close) with
  | Ok bar -> bar
  | Error error -> failwith error

let applied state bar =
  match Technical.update state bar with
  | Ok (Technical.Applied (state, reading)) -> state, reading
  | Ok Technical.Duplicate -> failwith "expected a new bar"
  | Error error -> failwith error

let () =
  let non_strategy_bar = `Assoc ["T", `String "b"; "S", `String "ETH/USD"] in
  check (Technical.is_btc_bar_event (event 4 100. 100. 100. 100.))
    "BTC archive warmup includes strategy symbol";
  check (not (Technical.is_btc_bar_event non_strategy_bar))
    "BTC archive warmup skips research symbols";
  let flat = ref Technical.empty in
  let last = ref None in
  (* SOURCE: Pattern Forge needs 50 closed bars to seed its slow EMA. *)
  for minute = 0 to 49 do
    let next, reading = applied !flat (parse minute 100. 100. 100. 100.) in
    flat := next;
    last := Some reading
  done;
  let reading = Option.get !last in
  check (reading.count = 50 && reading.trend = "mixed") "flat EMA warmup";
  check (reading.ema_fast = Some 100. && reading.ema_slow = Some 100.)
    "flat EMA values";
  check (reading.rsi = Some 50.) "flat Wilder RSI";
  check (reading.band_middle = Some 100. && reading.band_upper = Some 100.
         && reading.band_lower = Some 100.) "flat Bollinger values";
  let first, _ = applied Technical.empty (parse 0 101. 101. 100. 100.) in
  let second_bar = parse 1 99. 102. 99. 102. in
  let second, second_reading = applied first second_bar in
  check (List.mem "bullish_engulfing" second_reading.patterns)
    "adjacent engulfing shape";
  check (Technical.update second second_bar = Ok Technical.Duplicate)
    "identical duplicate ignored";
  let changed = parse 1 99. 103. 99. 102. in
  check (Result.is_error (Technical.update second changed))
    "conflicting duplicate rejected";
  let _, gap_reading = applied second (parse 3 100. 100. 100. 100.) in
  check (gap_reading.gap_reset && gap_reading.count = 1 &&
         gap_reading.trend = "warming") "missing minute resets indicators";
  check (Result.is_error (Technical.parse_bar (event 4 100. 99. 100. 100.)))
    "invalid OHLC rejected";
  let five_minute_first = parse 0 100. 100. 100. 100. in
  let five_minute_second = parse 5 101. 101. 101. 101. in
  let five_state = match Technical.update ~step:5 Technical.empty five_minute_first with
    | Ok (Technical.Applied (state, _)) -> state
    | _ -> failwith "first five-minute bar" in
  (match Technical.update ~step:5 five_state five_minute_second with
   | Ok (Technical.Applied (_, reading)) ->
     check (not reading.gap_reset && reading.count = 2)
       "adjacent five-minute bars stay contiguous"
   | _ -> failwith "second five-minute bar");
  print_endline "technical closed-bar checks passed"
