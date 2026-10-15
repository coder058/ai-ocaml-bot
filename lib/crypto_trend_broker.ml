(* BTC/USD month-end trend adapter. Alpaca PAPER origin only, BTC/USD only,
   its own client-ID namespace and gate. Not shared with the legacy BTC or
   multi-frame executors. *)
let prefix = "aibottrc"
let symbol = "BTC/USD"
let ledger_name = "crypto-trend-ledger.json"
(* SOURCE: IOC limit with a 50 bps marketable buffer, so a month-end decision
   fills like a taker order without accepting an unbounded market price.
   UNCALIBRATED GUESS; the backtest charged 27 bps per side. *)
let buffer = 0.005
(* SOURCE: at most three IOC attempts per side per decision month, so an
   unfilled IOC can retry without ever looping. UNCALIBRATED GUESS. *)
let max_attempts = 3

let client_id ~month ~side ~origin ~attempt =
  prefix ^ Digest.to_hex (Digest.string (String.concat "|"
    [symbol; month; side; origin; string_of_int attempt; Monthly_trend.crypto_policy]))

let body ~side ~qty ~limit_price ~client_order_id =
  if not (String.starts_with ~prefix client_order_id) ||
     not (String.for_all (function 'a'..'z'|'A'..'Z'|'0'..'9' -> true | _ -> false) client_order_id) then
    Error "crypto trend order ID is outside its namespace"
  else if side <> "buy" && side <> "sell" then Error "invalid order side"
  else if qty <= Exact_decimal.zero then Error "order quantity must be positive"
  else if not (Float.is_finite limit_price) || limit_price <= 0. then Error "invalid limit price"
  else Ok (Yojson.Safe.to_string (`Assoc [
    "symbol", `String symbol; "side", `String side; "qty", `String (Exact_decimal.to_string qty);
    "type", `String "limit"; "time_in_force", `String "ioc";
    "limit_price", `String (Printf.sprintf "%.9f" limit_price);
    "client_order_id", `String client_order_id]))

let submit ~side ~qty ~limit_price ~client_order_id =
  if Sys.getenv_opt "PAPER_ORDERS" <> Some "1" || Sys.getenv_opt "CRYPTO_TREND_ORDERS" <> Some "1" then
    Error "crypto trend paper gates are not armed"
  else Result.bind (body ~side ~qty ~limit_price ~client_order_id) (fun body ->
    Result.bind (Alpaca_config.validate_base_url Paper_broker.base) (fun () ->
      Result.bind (Paper_broker.credentials ()) (fun (key_id, secret) ->
        Alpaca_http.post_json ~url:(Paper_broker.base ^ "/v2/orders") ~key_id ~secret ~body)))

(* SOURCE: Alpaca v1beta3 US crypto daily bars. The exact daily-bar time-zone
   alignment is not verified here; only the bar's start date is used, and the
   scheduler waits until 12:00 UTC on the 1st before trusting a month close. *)
let daily_bars ~start =
  Result.bind (Paper_broker.credentials ()) (fun (key_id, secret) ->
    let rec page token count acc =
      if count > 20 then Error "crypto bar pagination did not terminate" else
      let url = "https://data.alpaca.markets/v1beta3/crypto/us/bars?symbols=BTC%2FUSD&timeframe=1Day&limit=10000&start="
        ^ start ^ (match token with Some t -> "&page_token=" ^ t | None -> "") in
      match Alpaca_http.get_json ~url ~key_id ~secret with
      | Error _ as error -> error
      | Ok doc ->
        let rows = match Option.bind (Paper_broker.member "bars" doc) (Paper_broker.member symbol) with
          | Some (`List rows) -> rows | _ -> [] in
        let parsed = List.map (fun row ->
          match Paper_broker.string (Paper_broker.member "t" row), Paper_broker.float (Paper_broker.member "c" row) with
          | Some t, Some close when String.length t >= 10 -> Some { Monthly_trend.date = String.sub t 0 10; close }
          | _ -> None) rows in
        if List.mem None parsed then Error "crypto daily bar is missing a time or close"
        else
          let acc = acc @ List.filter_map Fun.id parsed in
          match Paper_broker.string (Paper_broker.member "next_page_token" doc) with
          | Some t when t <> "" -> page (Some t) (count + 1) acc
          | _ -> Ok acc in
    page None 0 [])
