(* Incremental descriptive readings of Alpaca BTC/USD closed bars.
   Selected formulas are adapted from Pattern Forge's marketAnalysis.ts;
   cross-language parity has not been established. These readings are not
   probabilities and do not authorize a paper order. *)

type bar = {
  minute : int;
  timestamp : string;
  open_price : float;
  high : float;
  low : float;
  close : float;
  volume : float;
}

type ema = { count : int; sum : float; value : float option }

type state = {
  last : bar option;
  count : int;
  fast : ema;
  slow : ema;
  macd_fast : ema;
  macd_slow : ema;
  macd_signal : ema;
  rsi_changes : int;
  gain_sum : float;
  loss_sum : float;
  avg_gain : float option;
  avg_loss : float option;
  closes : float list;
}

type reading = {
  bar : bar;
  count : int;
  gap_reset : bool;
  patterns : string list;
  trend : string;
  ema_fast : float option;
  ema_slow : float option;
  rsi : float option;
  band_middle : float option;
  band_upper : float option;
  band_lower : float option;
  macd : float option;
  macd_signal : float option;
}

type update = Duplicate | Applied of state * reading

let empty_ema = { count = 0; sum = 0.; value = None }

let empty = {
  last = None; count = 0;
  fast = empty_ema; slow = empty_ema;
  macd_fast = empty_ema; macd_slow = empty_ema;
  macd_signal = empty_ema;
  rsi_changes = 0; gain_sum = 0.; loss_sum = 0.;
  avg_gain = None; avg_loss = None; closes = [];
}

(* SOURCE: Pattern Forge's default descriptive indicator windows. *)
let fast_period = 20
let slow_period = 50
let band_period = 20
let band_deviations = 2.
let rsi_period = 14
let macd_fast_period = 12
let macd_slow_period = 26
let macd_signal_period = 9

(* GUESS: # UNCALIBRATED GUESS — Pattern Forge's shape thresholds are
   exploratory geometry; they are not measured entry or exit parameters. *)
let doji_ratio = 0.1
let wick_ratio = 2.

let field name = function
  | `Assoc members -> List.assoc_opt name members
  | _ -> None

let number = function
  | Some (`Float n) -> Some n
  | Some (`Int n) -> Some (float_of_int n)
  | _ -> None

let string = function Some (`String value) -> Some value | _ -> None

let parse_utc_minute timestamp =
  (* SOURCE: Alpaca emits ISO UTC bar-start times such as 2026-09-27T12:41:00Z.
     The service sets TZ=UTC so Unix.mktime uses that calendar. *)
  try
    if String.length timestamp <> 20 || timestamp.[4] <> '-' ||
       timestamp.[7] <> '-' || timestamp.[10] <> 'T' ||
       timestamp.[13] <> ':' || timestamp.[16] <> ':' ||
       timestamp.[19] <> 'Z' then None
    else
      let part start length = int_of_string (String.sub timestamp start length) in
      let year = part 0 4 and month = part 5 2 and day = part 8 2 in
      let hour = part 11 2 and minute = part 14 2 and second = part 17 2 in
      if second <> 0 then None
      else
        let base = Unix.gmtime 0. in
        let calendar = { base with
          Unix.tm_year = year - 1900; tm_mon = month - 1; tm_mday = day;
          tm_hour = hour; tm_min = minute; tm_sec = second; tm_isdst = false } in
        let seconds, _ = Unix.mktime calendar in
        let check = Unix.gmtime seconds in
        if check.tm_year <> year - 1900 || check.tm_mon <> month - 1 ||
           check.tm_mday <> day || check.tm_hour <> hour ||
           check.tm_min <> minute || check.tm_sec <> second then None
        else Some (int_of_float seconds / 60)
  with _ -> None

let is_btc_bar_event event =
  (* SOURCE: the shared archive includes research symbols; this OCaml indicator
     state is intentionally scoped to Alpaca BTC/USD. *)
  string (field "T" event) = Some "b" &&
  string (field "S" event) = Some "BTC/USD"

let parse_bar ?(symbol = "BTC/USD") event =
  match string (field "T" event), string (field "S" event),
        string (field "t" event), number (field "o" event),
        number (field "h" event), number (field "l" event),
        number (field "c" event), number (field "v" event) with
  | Some "b", Some actual_symbol, Some timestamp,
    Some open_price, Some high, Some low, Some close, Some volume
    when actual_symbol = symbol ->
    (match parse_utc_minute timestamp with
     | Some minute when List.for_all Float.is_finite
         [ open_price; high; low; close; volume ] &&
         low > 0. && volume >= 0. &&
         high >= max open_price (max close low) &&
         low <= min open_price close ->
       Ok { minute; timestamp; open_price; high; low; close; volume }
     | _ -> Error "invalid closed-minute bar timestamp or OHLCV")
  | _ -> Error "closed bar symbol or fields do not match"

let next_ema period (prior : ema) close =
  let count = prior.count + 1 in
  let sum = prior.sum +. close in
  if count < period then { count; sum; value = None }
  else if count = period then
    { count; sum; value = Some (sum /. float_of_int period) }
  else
    let alpha = 2. /. float_of_int (period + 1) in
    let previous = Option.get prior.value in
    { count; sum; value = Some (close *. alpha +. previous *. (1. -. alpha)) }
  (* SOURCE: Pattern Forge seeds EMA with a full-window SMA, then uses
     the standard 2/(period+1) smoothing recurrence. *)

let take count values =
  let rec go remaining result = function
    | _ when remaining = 0 -> List.rev result
    | [] -> List.rev result
    | item :: rest -> go (remaining - 1) (item :: result) rest in
  go count [] values

let patterns ?(allow_session_gap = false) ~step (previous : bar option) (current : bar) =
  let body = abs_float (current.close -. current.open_price) in
  let range = current.high -. current.low in
  let lower = min current.open_price current.close -. current.low in
  let upper = current.high -. max current.open_price current.close in
  let names = ref [] in
  let add name = names := name :: !names in
  if range > 0. && body /. range <= doji_ratio then add "doji";
  if body > 0. && lower >= body *. wick_ratio && upper <= body then
    add "hammer_shape";
  if body > 0. && upper >= body *. wick_ratio && lower <= body then
    add "shooting_star_shape";
  (match previous with
   | Some older when older.minute + step = current.minute || allow_session_gap ->
     if older.close < older.open_price &&
        current.close > current.open_price &&
        current.open_price <= older.close && current.close >= older.open_price then
       add "bullish_engulfing";
     if older.close > older.open_price &&
        current.close < current.open_price &&
        current.open_price >= older.close && current.close <= older.open_price then
       add "bearish_engulfing"
   | _ -> ());
  List.rev !names

let update ?(step = 1) ?(allow_session_gap = false) (state : state) (bar : bar) =
  (* SOURCE: step=1 for Alpaca stream minute bars, step=5 for historical
     five-minute bars; a missing interval resets all indicators. *)
  match state.last with
  | Some previous when bar.minute = previous.minute ->
    if bar = previous then Ok Duplicate else Error "conflicting duplicate bar"
  | Some previous when bar.minute < previous.minute ->
    Error "out-of-order closed bar"
  | _ ->
    let gap_reset = match state.last with
      | Some previous -> bar.minute <> previous.minute + step && not allow_session_gap
      | None -> false in
    let state = if gap_reset then empty else state in
    let fast = next_ema fast_period state.fast bar.close in
    let slow = next_ema slow_period state.slow bar.close in
    let macd_fast = next_ema macd_fast_period state.macd_fast bar.close in
    let macd_slow = next_ema macd_slow_period state.macd_slow bar.close in
    let macd = match macd_fast.value, macd_slow.value with
      | Some fast, Some slow -> Some (fast -. slow)
      | _ -> None in
    let macd_signal = match macd with
      | Some line -> next_ema macd_signal_period state.macd_signal line
      | None -> state.macd_signal in
    let rsi_changes, gain_sum, loss_sum, avg_gain, avg_loss =
      match state.last with
      | None -> state.rsi_changes, state.gain_sum, state.loss_sum,
        state.avg_gain, state.avg_loss
      | Some previous ->
        let change = bar.close -. previous.close in
        let gain = max 0. change and loss = max 0. (-.change) in
        let count = state.rsi_changes + 1 in
        if count < rsi_period then
          count, state.gain_sum +. gain, state.loss_sum +. loss, None, None
        else if count = rsi_period then
          let gains = state.gain_sum +. gain and losses = state.loss_sum +. loss in
          count, gains, losses,
          Some (gains /. float_of_int rsi_period),
          Some (losses /. float_of_int rsi_period)
        else
          let old_gain = Option.get state.avg_gain in
          let old_loss = Option.get state.avg_loss in
          count, state.gain_sum, state.loss_sum,
          Some ((old_gain *. float_of_int (rsi_period - 1) +. gain) /.
            float_of_int rsi_period),
          Some ((old_loss *. float_of_int (rsi_period - 1) +. loss) /.
            float_of_int rsi_period) in
    let rsi = match avg_gain, avg_loss with
      | Some gain, Some loss ->
        Some (if gain = 0. && loss = 0. then 50.
              else if loss = 0. then 100.
              else 100. -. 100. /. (1. +. gain /. loss))
      | _ -> None in
    (* SOURCE: Wilder RSI seeding and recurrence in Pattern Forge. *)
    let closes = take band_period (bar.close :: state.closes) in
    let band_middle, band_upper, band_lower =
      if List.length closes < band_period then None, None, None
      else
        let mean = List.fold_left (+.) 0. closes /. float_of_int band_period in
        let variance = List.fold_left (fun total value ->
          total +. (value -. mean) ** 2.) 0. closes /.
          float_of_int band_period in
        let deviation = sqrt variance *. band_deviations in
        Some mean, Some (mean +. deviation), Some (mean -. deviation) in
    (* SOURCE: Pattern Forge uses a 20-close population standard deviation. *)
    let trend = match fast.value, slow.value with
      | Some fast, Some slow when bar.close > fast && fast > slow -> "rising"
      | Some fast, Some slow when bar.close < fast && fast < slow -> "falling"
      | Some _, Some _ -> "mixed"
      | _ -> "warming" in
    let reading = {
      bar; count = state.count + 1; gap_reset;
      patterns = patterns ~step ~allow_session_gap state.last bar; trend;
      ema_fast = fast.value; ema_slow = slow.value; rsi;
      band_middle; band_upper; band_lower;
      macd; macd_signal = macd_signal.value;
    } in
    Ok (Applied ({ last = Some bar; count = state.count + 1;
      fast; slow; macd_fast; macd_slow; macd_signal;
      rsi_changes; gain_sum; loss_sum; avg_gain; avg_loss; closes }, reading))
