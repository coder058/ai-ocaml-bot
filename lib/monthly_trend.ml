(* Month-end 200-session trend policy for liquid US ETFs. Pure; no network.
   Selected by research/cost_aware_backtest.py (`sma_trend_monthly`) after a
   frozen develop/validate split and one holdout opening; see
   docs/PROFITABILITY-REVIEW.md. Simulated holdout results are not live
   profitability, and this module grants no order authority by itself. *)
type bar = { date : string; close : float }
(* [date] is the New York session date, YYYY-MM-DD. *)
type decision = Hold | Flat
type reading = { decision : decision; month : string; last_date : string; close : float; average : float }

let policy = "monthly_trend_v1"
(* SOURCE: 200 daily sessions, the moving-average window evaluated in the
   backtest. Fixed from published practice before the screen; not fitted. *)
let lookback = 200
(* SOURCE: Thursday holiday plus weekend is a four-day calendar gap; allow one
   spare day. Longer gaps mean missing data and fail closed. *)
let max_gap_days = 5

let parse_date text =
  if String.length text <> 10 || text.[4] <> '-' || text.[7] <> '-' then None
  else match int_of_string_opt (String.sub text 0 4), int_of_string_opt (String.sub text 5 2),
             int_of_string_opt (String.sub text 8 2) with
    | Some y, Some m, Some d when m >= 1 && m <= 12 && d >= 1 && d <= 31 -> Some (y, m, d)
    | _ -> None

let leap y = (y mod 4 = 0 && y mod 100 <> 0) || y mod 400 = 0
let days_in_month y m = match m with
  | 2 -> if leap y then 29 else 28
  | 4 | 6 | 9 | 11 -> 30
  | _ -> 31

(* SOURCE: Howard Hinnant's days_from_civil algorithm (proleptic Gregorian). *)
let day_number (y, m, d) =
  let y = if m <= 2 then y - 1 else y in
  let era = (if y >= 0 then y else y - 399) / 400 in
  let yoe = y - era * 400 in
  let mp = (m + 9) mod 12 in
  let doy = (153 * mp + 2) / 5 + d - 1 in
  let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy in
  era * 146097 + doe - 719468

let month_key (y, m, _) = Printf.sprintf "%04d-%02d" y m
let previous_month (y, m, _) = if m = 1 then (y - 1, 12, 1) else (y, m - 1, 1)

let decide ~today bars =
  let parsed = List.map (fun bar -> parse_date bar.date, bar) bars in
  if List.exists (fun (date, (bar : bar)) -> date = None || not (Float.is_finite bar.close) || bar.close <= 0.) parsed then
    Error "daily bar has an invalid date or close"
  else
    let parsed = List.map (fun (date, bar) -> Option.get date, bar) parsed in
    let rec increasing = function
      | (a, _) :: ((b, _) :: _ as rest) -> day_number a < day_number b && increasing rest
      | _ -> true in
    if not (increasing parsed) then Error "daily bars are not strictly increasing"
    else
      let current = month_key today in
      let completed = List.filter (fun (date, _) -> month_key date < current) parsed in
      let window = List.filteri (fun i _ -> i >= List.length completed - lookback) completed in
      match List.rev window with
      | [] -> Error "no completed-month daily bars"
      | (last_date, (last : bar)) :: _ ->
        let expected = previous_month today in
        let (ey, em, _) = expected in
        if month_key last_date <> month_key expected then
          Error "latest completed month is missing; data are stale"
        else if day_number (ey, em, days_in_month ey em) - day_number last_date > max_gap_days then
          Error "previous month's final session is missing"
        else if List.length window < lookback then Error "insufficient daily history for the 200-session average"
        else
          let rec gaps = function
            | (a, _) :: ((b, _) :: _ as rest) -> day_number b - day_number a <= max_gap_days && gaps rest
            | _ -> true in
          if not (gaps window) then Error "daily history has a gap; average not calculated"
          else
            let average = List.fold_left (fun sum (_, (bar : bar)) -> sum +. bar.close) 0. window /. float_of_int lookback in
            Ok { decision = (if last.close > average then Hold else Flat);
                 month = month_key last_date; last_date = last.date; close = last.close; average }

let client_id ~symbol ~month ~side ~origin =
  Stock_policy.client_id [symbol; month; side; origin; policy]

let bars_to_json bars = `List (List.map (fun bar -> `List [`String bar.date; `Float bar.close]) bars)
let bars_of_json = function
  | `List rows ->
    (try Ok (List.map (function
        | `List [`String date; close] ->
          (match Paper_broker.float (Some close) with
           | Some close -> { date; close } | None -> failwith "close")
        | _ -> failwith "row") rows)
     with _ -> Error "evidence bars are malformed")
  | _ -> Error "evidence bars are missing"

let reading_to_json r =
  `Assoc ["decision", `String (if r.decision = Hold then "hold" else "flat"); "month", `String r.month;
          "lastSession", `String r.last_date; "close", `Float r.close; "average200", `Float r.average]

(* Recompute the decision from the intent's own retained bars, so a stale or
   edited intent cannot submit an order the rule would not make today. *)
let verify_intent ~today ~symbol ~side ~client_id:cid evidence =
  let text name = Paper_broker.string (Paper_broker.member name evidence) in
  if text "policy" <> Some policy || text "symbol" <> Some symbol || text "side" <> Some side
     || text "clientOrderId" <> Some cid then Error "trend intent identity mismatch"
  else
    Result.bind (bars_of_json (Option.value ~default:`Null (Paper_broker.member "bars" evidence))) (fun bars ->
      Result.bind (decide ~today bars) (fun reading ->
        let origin = Option.value ~default:"" (text "originEntryId") in
        if side = "buy" && reading.decision <> Hold then Error "trend rule no longer holds this ETF"
        else if side = "sell" && reading.decision <> Flat then Error "trend rule no longer exits this ETF"
        else if side <> "buy" && side <> "sell" then Error "invalid trend side"
        else if client_id ~symbol ~month:reading.month ~side ~origin <> cid then
          Error "trend client ID does not match the decision month"
        else Ok reading))
