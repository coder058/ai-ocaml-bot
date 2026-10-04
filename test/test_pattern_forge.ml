open Paper_market

(* # SOURCE: all candles below are SYNTHETIC branch fixtures, not market data. *)
let check ok msg = if not ok then failwith msg

let candle close_time close =
  `Assoc [
    "closeTime", `Int close_time;
    "c", `Float close;
    "closed", `Bool true;
  ]

let snapshot frames =
  `Assoc [
    "symbol", `String "BTC";
    "venue", `String "Hyperliquid";
    "frames", `Assoc [ "5m", `List frames ];
  ]

let () =
  (* # SOURCE: five minutes equals 300,000 milliseconds. *)
  let a = candle 300_000 100. and b = candle 600_000 101. in
  let result = Pattern_forge.parse_frame ~symbol:"BTC" ~timeframe:"5m"
    ~now_ms:600_000 (snapshot [ a; b ]) in
  check (match result with Ok r -> r.return_pct > 0.99 && r.return_pct < 1.01
       | Error _ -> false) "adjacent closed candles return";
  let gap = Pattern_forge.parse_frame ~symbol:"BTC" ~timeframe:"5m"
    ~now_ms:900_000 (snapshot [ a; candle 900_000 101. ]) in
  check (Result.is_error gap) "missing interval is unavailable";
  let future = Pattern_forge.parse_frame ~symbol:"BTC" ~timeframe:"5m"
    ~now_ms:599_999 (snapshot [ a; b ]) in
  check (Result.is_error future) "future candle is unavailable";
  let wrong = Pattern_forge.parse_frame ~symbol:"ETH" ~timeframe:"5m"
    ~now_ms:600_000 (snapshot [ a; b ]) in
  check (Result.is_error wrong) "symbol mismatch is unavailable";
  print_endline "Pattern Forge closed-candle checks passed"
