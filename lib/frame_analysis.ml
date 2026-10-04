(* Shared, descriptive Pattern Forge indicators for every venue/frame.
   No broker or network function is called here. Candidate geometry is an
   exploratory policy, not a calibrated probability or order instruction. *)

let frames = [ "1m", 1; "5m", 5; "30m", 30; "1h", 60; "4h", 240 ]
(* SOURCE: the user's five requested UTC timeframes, in minutes. *)

let number value = match value with None -> `Null | Some n -> `Float n
let strings values = `List (List.map (fun value -> `String value) values)

let invalid reason = `Assoc [
  "status", `String "invalid"; "reason", `String reason;
  "candidate", `Null; "orderAuthority", `Bool false;
  "winProbability", `Null;
]

let describe ?(expected_starts = []) ?(session_open = true)
    ~symbol ~minutes ~as_of_minute rows =
  (* SOURCE: equity expected_starts comes from the broker's actual session
     calendar. A closed overnight/weekend is not a missing feed candle. *)
  let successors = Hashtbl.create (List.length expected_starts) in
  let rec connect = function
    | first :: (second :: _ as rest) -> Hashtbl.replace successors first second; connect rest
    | _ -> () in
  connect expected_starts;
  let rec apply state previous last count gaps = function
    | [] -> Ok (previous, last, count, gaps)
    | row :: remaining ->
      let fields = match row with `Assoc fields -> fields | _ -> [] in
      let event = `Assoc (("T", `String "b") :: ("S", `String symbol) ::
        List.filter (fun (name, _) -> name <> "T" && name <> "S") fields) in
      (match Technical.parse_bar ~symbol event with
       | Error error -> Error error
       | Ok bar when bar.minute mod minutes <> 0 -> Error "bar is not frame aligned"
       | Ok bar when bar.minute + minutes > as_of_minute ->
         Error "bar has not closed at analysis time"
       | Ok bar ->
         let allow_session_gap = match state.Technical.last with
           | Some prior -> Hashtbl.find_opt successors prior.minute = Some bar.minute
           | None -> false in
         (match Technical.update ~step:minutes ~allow_session_gap state bar with
          | Error error -> Error error
          | Ok Technical.Duplicate -> apply state previous last count gaps remaining
          | Ok (Technical.Applied (next, reading)) ->
            apply next (if reading.gap_reset then None else last) (Some reading)
              (count + 1) (gaps + if reading.gap_reset then 1 else 0) remaining)) in
  match apply Technical.empty None None 0 0 rows with
  | Error error -> invalid error
  | Ok (_, None, _, _) -> `Assoc [
      "status", `String "no_data"; "reason", `String "No closed candles returned";
      "completeBars", `Int 0; "contiguousTailBars", `Int 0;
      "candidate", `Null; "orderAuthority", `Bool false;
      "winProbability", `Null;
    ]
  | Ok (previous, Some (reading : Technical.reading), count, gaps) ->
    let bar = reading.bar in
    let expected_start = if expected_starts = [] then
        as_of_minute / minutes * minutes - minutes
      else List.fold_left (fun last minute ->
        if minute + minutes <= as_of_minute then minute else last) (-1) expected_starts in
    let fresh = bar.minute = expected_start in
    let warmed = reading.ema_slow <> None in
    let bullish = List.exists (fun pattern -> List.mem pattern
      [ "bullish_engulfing"; "hammer_shape" ]) reading.patterns in
    let bearish = List.exists (fun pattern -> List.mem pattern
      [ "bearish_engulfing"; "shooting_star_shape" ]) reading.patterns in
    (* GUESS: # UNCALIBRATED GUESS — exploratory confluence of EMA trend
       and a candle shape; frozen for forward measurement, not broker authority. *)
    let candidate = if fresh && warmed && session_open && reading.trend = "rising" && bullish
      then Some "long" else if fresh && warmed && session_open && reading.trend = "falling" && bearish
      then Some "short" else None in
    let structure = match previous with
      | Some (prior : Technical.reading) when
          bar.high > prior.bar.high && bar.low > prior.bar.low -> "higher_high_higher_low"
      | Some prior when bar.high < prior.bar.high && bar.low < prior.bar.low ->
          "lower_high_lower_low"
      | Some _ -> "overlapping"
      | None -> "unavailable" in
    (* SOURCE: compare the last two closed candles' actual highs/lows;
       this is a minimal trend-structure reading, not full Murphy methodology. *)
    let invalidation = match candidate with
      | Some "long" when bar.low < bar.close -> Some bar.low
      | Some "short" when bar.high > bar.close -> Some bar.high
      | _ -> None in
    let status, reason =
      if not session_open then "market_closed", "Regular equity session is closed"
      else if not fresh then "stale", "Latest completed frame is missing"
      else if not warmed then "warming", Printf.sprintf
        "Need %d consecutive bars for EMA%d; have %d"
        Technical.slow_period Technical.slow_period reading.count
      else match candidate with
        | Some side -> "candidate", side ^ " trend and candle shape; evidence gate pending"
        | None -> "ready", "No trend and candle-shape confluence on this close" in
    `Assoc [
      "status", `String status; "reason", `String reason;
      "completeBars", `Int count; "contiguousTailBars", `Int reading.count;
      "gapResets", `Int gaps; "lastBarStart", `String bar.timestamp;
      "ageMinutesAfterClose", `Int (as_of_minute - bar.minute - minutes);
      "close", `Float bar.close; "trend", `String reading.trend;
      "structure", `String structure; "candleShapes", strings reading.patterns;
      "ema20", number reading.ema_fast; "ema50", number reading.ema_slow;
      "rsi14", number reading.rsi; "macd", number reading.macd;
      "macdSignal", number reading.macd_signal;
      "bollingerMiddle", number reading.band_middle;
      "bollingerUpper", number reading.band_upper;
      "bollingerLower", number reading.band_lower;
      "candidate", (match candidate with None -> `Null | Some side -> `String side);
      "invalidationLevel", number invalidation;
      "stopOrderPlaced", `Bool false; "orderAuthority", `Bool false;
      "winProbability", `Null;
    ]

let analyze document =
  let field = Technical.field in
  match Technical.string (field "asOf" document), field "markets" document with
  | Some as_of, Some (`List markets) ->
    (match Technical.parse_utc_minute as_of with
     | None -> Error "asOf must be a UTC minute boundary"
     | Some as_of_minute ->
       let analyze_market market =
         match Technical.string (field "symbol" market),
               Technical.string (field "venue" market), field "frames" market with
         | Some symbol, Some venue, Some frame_rows ->
           let session_open = match field "sessionOpen" market with
             | Some (`Bool value) -> value | _ -> true in
           let readings = List.map (fun (name, minutes) ->
             let expected_starts = match Option.bind (field "expectedStarts" market) (field name) with
               | Some (`List values) -> List.filter_map (function `Int minute -> Some minute | _ -> None) values
               | _ -> [] in
             name, match field name frame_rows with
               | Some (`List rows) -> describe ~expected_starts ~session_open ~symbol ~minutes ~as_of_minute rows
               | _ -> invalid "frame array missing") frames in
           `Assoc [ "symbol", `String symbol; "venue", `String venue;
                    "frames", `Assoc readings ]
         | _ -> invalid "market venue, symbol or frames missing" in
       Ok (`Assoc [ "asOf", `String as_of; "markets", `List (List.map analyze_market markets);
           "engine", `String "OCaml Technical / Pattern Forge formulas";
           "policy", `String "trend_candle_confluence_v1";
           "orderAuthority", `Bool false; "winProbability", `Null ]))
  | _ -> Error "batch document is missing asOf or markets"
