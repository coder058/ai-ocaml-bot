open Paper_market

(* SOURCE: all OHLC values, symbols and dates below are synthetic fixtures.
   They test causality, cross-symbol formulas and gaps, not trading returns. *)
let check condition message = if not condition then failwith message
let epoch_minute = 29_500_000
let utc minute =
  let tm = Unix.gmtime (float_of_int minute *. 60.) in
  Printf.sprintf "%04d-%02d-%02dT%02d:%02d:00Z"
    (tm.tm_year + 1900) (tm.tm_mon + 1) tm.tm_mday tm.tm_hour tm.tm_min
let field name json = Option.get (Technical.field name json)
let bar minute value = `Assoc [ "t", `String (utc minute);
  "o", `Float value; "h", `Float (value +. 1.); "l", `Float (value -. 1.);
  "c", `Float value; "v", `Float 1. ]
let rows minutes =
  let start = epoch_minute / minutes * minutes in
  List.init Technical.slow_period (fun index -> bar (start + index * minutes) 100.)

let () =
  List.iter (fun (_, minutes) ->
    let candles = rows minutes in
    let end_minute = epoch_minute / minutes * minutes + Technical.slow_period * minutes in
    let btc = Frame_analysis.describe ~symbol:"BTC/USD" ~minutes
        ~as_of_minute:end_minute candles in
    let eur = Frame_analysis.describe ~symbol:"xyz:EUR" ~minutes
        ~as_of_minute:end_minute candles in
    check (btc = eur) "same data uses same formulas across venue symbols";
    check (field "status" eur = `String "ready") "all requested frames warm correctly";
    check (field "ema50" eur = `Float 100.) "full-window slow EMA seed";
    check (field "winProbability" eur = `Null && field "orderAuthority" eur = `Bool false)
      "descriptions have no probability or order authority";
    let future = Frame_analysis.describe ~symbol:"ETH/USD" ~minutes
      ~as_of_minute:(end_minute - minutes) candles in
    check (field "status" future = `String "invalid") "future close rejected";
    let stale = Frame_analysis.describe ~symbol:"ETH/USD" ~minutes
      ~as_of_minute:(end_minute + minutes) candles in
    check (field "status" stale = `String "stale") "missing newest frame is visible";
    let gap = Frame_analysis.describe ~symbol:"ETH/USD" ~minutes
      ~as_of_minute:(end_minute + minutes)
      (List.filteri (fun index _ -> index <> Technical.slow_period - 1) candles @
       [bar end_minute 101.]) in
    check (field "status" gap = `String "warming" &&
           field "contiguousTailBars" gap = `Int 1) "gap resets cross-frame warmup"
  ) Frame_analysis.frames;
  (* SOURCE: synthetic sessions separated by a scheduled closure. Only
     adjacent slots in the explicitly supplied calendar may bridge that gap. *)
  let scheduled = List.init Technical.slow_period (fun index -> epoch_minute / 60 * 60 + index * 1440) in
  let session_rows = List.map (fun minute -> bar minute 100.) scheduled in
  let last = List.hd (List.rev scheduled) in
  let equity = Frame_analysis.describe ~expected_starts:scheduled ~session_open:false
    ~symbol:"DIA" ~minutes:60 ~as_of_minute:(last + 60) session_rows in
  check (field "ema50" equity = `Float 100. &&
         field "status" equity = `String "market_closed") "scheduled overnight preserves indicator warmup";
  let missed_session = Frame_analysis.describe ~expected_starts:scheduled
    ~symbol:"DIA" ~minutes:60 ~as_of_minute:(last + 60)
    (List.filteri (fun index _ -> index <> Technical.slow_period - 2) session_rows) in
  check (field "contiguousTailBars" missed_session = `Int 1)
    "missing scheduled slot still resets equity warmup";
  print_endline "shared frame analysis causal checks passed"
