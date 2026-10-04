(* Stocks/ETF adapter. Trading origin is inherited from the hardcoded Alpaca
   paper adapter; it is never configurable. This is routing, not a strategy. *)
type asset = { symbol : string; fractionable : bool }
let field = Paper_broker.member
let string = Paper_broker.string
let symbol value =
  (* SOURCE: listed ticker syntax, and the user's protected AAPL inventory. *)
  if value="AAPL" then Error "AAPL is protected"
  else if value="" || not (String.for_all (function
    | 'A'..'Z' | '0'..'9' | '.' | '-' -> true | _ -> false) value) then
    Error "invalid stock ticker"
  else Ok value
let asset ticker = Result.bind (symbol ticker) (fun ticker ->
  Result.bind (Paper_broker.get ("/v2/assets/" ^ ticker)) (fun row ->
    match string (field "symbol" row), string (field "class" row),
          string (field "status" row), Paper_broker.bool (field "tradable" row),
          Paper_broker.bool (field "fractionable" row) with
    | Some returned,Some "us_equity",Some "active",Some true,Some fractionable
        when returned=ticker -> Ok {symbol=ticker;fractionable}
    | _ -> Error "ticker is not an active tradable US equity/ETF"))
let session_open () = Result.bind (Paper_broker.get "/v2/clock") (fun row ->
  match Paper_broker.bool (field "is_open" row) with
  | Some true -> Ok () | Some false -> Error "regular equity session is closed"
  | _ -> Error "broker clock is unavailable")
let positions () = Paper_crypto_broker.positions ()
let account () = Result.bind (Paper_broker.get "/v2/account") (fun row ->
  match string (field "status" row),Paper_broker.bool (field "trading_blocked" row),
        Paper_broker.float (field "non_marginable_buying_power" row) with
  | Some status,Some blocked,Some power when Float.is_finite power && power>=0. ->
    Ok (status,blocked,power)
  | _ -> Error "stock account fields are missing or invalid")
let quantity ticker rows =
  let matches=List.filter (fun row -> string (field "symbol" row)=Some ticker) rows in
  match matches with
  | [] -> Ok Exact_decimal.zero
  | [row] -> (match string (field "qty" row),string (field "side" row) with
      | Some text,Some "long" -> Exact_decimal.of_string text
      | _ -> Error "position is not an exact long quantity")
  | _ -> Error "duplicate stock position"
let quotes tickers =
  if List.exists (fun ticker -> Result.is_error (symbol ticker)) tickers then Error "invalid quote ticker"
  else Result.bind (Paper_broker.credentials ()) (fun (key_id,secret) ->
    (* SOURCE: the authenticated free IEX latest-quotes endpoint; this feed
       is not consolidated SIP. Never describe these quotes as full NBBO. *)
    let url="https://data.alpaca.markets/v2/stocks/quotes/latest?feed=iex&symbols=" ^
      String.concat "%2C" tickers in
    Alpaca_http.get_json ~url ~key_id ~secret)
let body ~asset ~side ~amount ~client_order_id =
  if not (String.starts_with ~prefix:"aibotstk" client_order_id) ||
     not (String.for_all (function 'a'..'z'|'A'..'Z'|'0'..'9' -> true | _ -> false) client_order_id) then
    Error "stock order ID is outside the owned namespace"
  else Result.bind (symbol asset.symbol) (fun ticker ->
    Result.bind (Exact_decimal.of_string amount) (fun value ->
      if value <= Exact_decimal.zero then Error "stock order amount must be positive"
      else if side="buy" && not asset.fractionable then
        Error "notional entries require a fractionable stock"
      else if side="buy" && value > Int64.mul 500L Exact_decimal.scale then
        (* SOURCE: user's maximum requested per-order dollar tier is $500;
           this routing cap is not probability calibration or an allocation. *)
        Error "stock entry exceeds the user dollar cap"
      else if side<>"buy" && side<>"sell" then Error "invalid order side"
      else Ok (Yojson.Safe.to_string (`Assoc ["symbol",`String ticker;
        "side",`String side; "type",`String "market"; "time_in_force",`String "day";
        (* SOURCE: Alpaca fractional stock orders accept notional OR qty with
           DAY time in force; neither both fields nor crypto IOC is used. *)
        (if side="buy" then "notional" else "qty"),`String (Exact_decimal.to_string value);
        "client_order_id",`String client_order_id]))))
let submit ~asset ~side ~amount ~client_order_id =
  if Sys.getenv_opt "PAPER_ORDERS"<>Some "1" || Sys.getenv_opt "STOCK_PAPER_ORDERS"<>Some "1" then
    Error "stock paper execution gates are not armed"
  else Result.bind (session_open ()) (fun () ->
    Result.bind (body ~asset ~side ~amount ~client_order_id) (fun body ->
      Result.bind (Alpaca_config.validate_base_url Paper_broker.base) (fun () ->
        Result.bind (Paper_broker.credentials ()) (fun (key_id,secret) ->
          Alpaca_http.post_json ~url:(Paper_broker.base ^ "/v2/orders") ~key_id ~secret ~body))))
