(* Read-only, closed-candle context from the author's Pattern Forge service.
   These measurements never authorize an Alpaca order. *)

type reading = {
  symbol : string;
  timeframe : string;
  close_time_ms : int;
  close : float;
  prior_close : float;
  return_pct : float;
}

let field name = function
  | `Assoc fields -> List.assoc_opt name fields
  | _ -> None

let string = function Some (`String x) -> Some x | _ -> None
let integer = function Some (`Int x) -> Some x | _ -> None
let number = function
  | Some (`Float x) -> Some x
  | Some (`Int x) -> Some (float_of_int x)
  | _ -> None

let interval_ms = function
  (* # SOURCE: the Pattern Forge public API names these UTC-aligned frames;
     millisecond durations follow from the standard time units. *)
  | "5m" -> Some 300_000
  | "1h" -> Some 3_600_000
  | "1d" -> Some 86_400_000
  | _ -> None

let parse_bar ~now_ms json =
  match integer (field "closeTime" json), number (field "c" json),
        field "closed" json with
  | Some close_time_ms, Some close, Some (`Bool true)
    when close_time_ms > 0 && close_time_ms <= now_ms &&
         Float.is_finite close && close > 0. ->
    Ok (close_time_ms, close)
  | _ -> Error "candle is malformed, open, or in the future"

let last_two_closed ~now_ms json =
  match json with
  | `List bars ->
    let rec gather prior current = function
      | [] ->
        (match prior, current with
         | Some a, Some b -> Ok (a, b)
         | _ -> Error "fewer than two valid closed candles")
      | row :: rest ->
        (match parse_bar ~now_ms row with
         | Error e -> Error e
         | Ok bar ->
           (match current with
            | Some (old_time, _) when fst bar <= old_time ->
              Error "candle close times are not strictly increasing"
            | _ -> gather current (Some bar) rest))
    in
    gather None None bars
  | _ -> Error "frame is not an array"

let parse_frame ~symbol ~timeframe ~now_ms snapshot =
  match interval_ms timeframe with
  | None -> Error "unsupported timeframe"
  | Some interval ->
    (match string (field "symbol" snapshot),
           string (field "venue" snapshot),
           Option.bind (field "frames" snapshot) (field timeframe) with
     | Some actual_symbol, Some "Hyperliquid", Some frame
       when actual_symbol = symbol ->
       (match last_two_closed ~now_ms frame with
        | Error e -> Error e
        | Ok ((prior_time, prior_close), (close_time_ms, close)) ->
          if close_time_ms - prior_time <> interval then
            Error "latest candles have a gap"
          else Ok {
            symbol; timeframe; close_time_ms; close; prior_close;
            (* # SOURCE: percentage return is (current/prior - 1) * 100. *)
            return_pct = (close /. prior_close -. 1.) *. 100.;
          })
     | _ -> Error "snapshot symbol, venue, or frame is unavailable")

let fetch symbol =
  if not (List.mem symbol [ "BTC"; "ETH"; "SOL" ]) then
    Error "Pattern Forge only serves BTC, ETH, and SOL live snapshots"
  else
    let url = "https://pattern-forge-five.vercel.app/api/markets/" ^ symbol in
    match Alpaca_http.get_public_json ~url with
    | Error e -> Error e
    | Ok snapshot ->
      (* # SOURCE: Unix.gettimeofday is seconds since epoch. *)
      let now_ms = int_of_float (Unix.gettimeofday () *. 1000.) in
      Ok (List.map (fun timeframe ->
        timeframe, parse_frame ~symbol ~timeframe ~now_ms snapshot)
        [ "5m"; "1h"; "1d" ])
