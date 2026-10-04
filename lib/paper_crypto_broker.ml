(* Explicit multi-crypto PAPER adapter. The existing BTC adapter remains
   unchanged. No equities, wallet signing or configurable trading host. *)

type asset = { symbol : string; tick : float; step : float; minimum : float;
               step_text : string }
type quote = { timestamp : string; minute : int; seconds : float;
               bid : float; ask : float }

let field = Paper_broker.member
let string = Paper_broker.string
let number = Paper_broker.float
let positive = function
  | Some value when Float.is_finite value && value > 0. -> Some value
  | _ -> None

let canonical symbol =
  let symbol = String.uppercase_ascii symbol in
  let compact = String.concat "" (String.split_on_char '/' symbol) in
  (* SOURCE: this adapter is restricted to alphanumeric asset codes quoted USD;
     the broker asset's class is also checked before submitting any order. *)
  if String.length compact <= String.length "USD" ||
     not (String.ends_with ~suffix:"USD" compact) ||
     not (String.for_all (function 'A' .. 'Z' | '0' .. '9' -> true | _ -> false) compact) ||
     (String.contains symbol '/' && symbol <> String.sub compact 0
        (String.length compact - String.length "USD") ^ "/USD") then
    Error "only canonical crypto/USD symbols are accepted"
  else Ok (String.sub compact 0 (String.length compact - String.length "USD") ^ "/USD")

let compact symbol = String.concat "" (String.split_on_char '/' symbol)
let same_symbol left right = match canonical left, canonical right with
  | Ok left, Ok right -> left = right | _ -> false

(* SOURCE: user's explicit crypto entry universe. Other assets can only be
   reduced by the existing owned-position wind-down path, never newly bought. *)
let allowed_entry symbol = match canonical symbol with
  | Ok ("BTC/USD" | "ETH/USD" | "SOL/USD") -> true | _ -> false

let asset symbol = match canonical symbol with
  | Error _ as error -> error
  | Ok symbol ->
    match Paper_broker.get ("/v2/assets/" ^ compact symbol) with
    | Error _ as error -> error
    | Ok document ->
      match string (field "symbol" document), string (field "class" document),
            string (field "status" document), Paper_broker.bool (field "tradable" document),
            positive (number (field "price_increment" document)),
            positive (number (field "min_trade_increment" document)),
            positive (number (field "min_order_size" document)) with
      | Some returned, Some "crypto", Some "active", Some true,
          Some tick, Some step, Some minimum when same_symbol returned symbol ->
        (match string (field "min_trade_increment" document) with
         | Some step_text -> Ok { symbol; tick; step; minimum; step_text }
         | None -> Error "asset quantity increment must retain decimal text")
      | _ -> Error "asset is not an active tradable USD crypto with valid increments"

let positions () = match Paper_broker.get "/v2/positions" with
  | Error _ as error -> error
  | Ok (`List items) -> Ok items
  | Ok _ -> Error "positions response was not an array"

let quantity symbol positions =
  let matches = List.filter (fun row ->
    match string (field "symbol" row) with
    | Some returned -> same_symbol returned symbol | None -> false) positions in
  match matches with
  | [] -> Ok 0.
  | [ row ] -> (match number (field "qty" row) with
      | Some value when Float.is_finite value && value >= 0. -> Ok value
      | _ -> Error "broker position is not a finite long quantity")
  | _ -> Error "duplicate broker position"

let quantity_exact symbol positions =
  let matches = List.filter (fun row -> match string (field "symbol" row) with
    | Some returned -> same_symbol returned symbol | None -> false) positions in
  match matches with
  | [] -> Ok Exact_decimal.zero
  | [row] -> (match string (field "qty" row) with
      | Some text -> Exact_decimal.of_string text
      | None -> Error "position quantity must retain broker decimal text")
  | _ -> Error "duplicate broker position"

let open_orders () = match Paper_broker.get "/v2/orders?status=open" with
  | Error _ as error -> error
  | Ok (`List items) -> Ok items
  | Ok _ -> Error "open orders response was not an array"

let has_open_order symbol rows = List.exists (fun row ->
  match string (field "symbol" row) with
  | Some returned -> same_symbol returned symbol
  | None -> true (* SOURCE: unknown order identity must block new submissions. *)) rows

let parse_quote symbol document =
  let quotes = Option.bind (field "quotes" document) (field symbol) in
  match quotes with
  | None -> Error "latest quote missing"
  | Some row ->
    match string (field "t" row), positive (number (field "bp" row)),
          positive (number (field "ap" row)) with
    | Some timestamp, Some bid, Some ask when bid <= ask ->
      (* SOURCE: Alpaca quote UTC timestamps include fractional seconds. The
         minute parser is reused; suffix is accepted only when numeric + Z. *)
      (try
        let minute_stamp = String.sub timestamp 0 16 ^ ":00Z" in
        let seconds_text = String.sub timestamp 17 (String.length timestamp - 18) in
        if timestamp.[String.length timestamp - 1] <> 'Z' ||
           not (String.for_all (function '0' .. '9' | '.' -> true | _ -> false) seconds_text)
        then Error "quote timestamp is not UTC"
        else match Technical.parse_utc_minute minute_stamp with
          | Some minute ->
            let seconds = float_of_string seconds_text in
            (* SOURCE: UTC minute seconds lie in [0,60), excluding leap second
               quotes until their handling is explicitly implemented. *)
            if Float.is_finite seconds && seconds >= 0. && seconds < 60. then
              Ok {timestamp; minute; seconds; bid; ask}
            else Error "invalid quote seconds"
          | None -> Error "invalid quote calendar"
       with _ -> Error "invalid quote timestamp")
    | _ -> Error "invalid quote prices"

let quote_document symbols =
  let canonical = List.map canonical symbols in
  if List.exists Result.is_error canonical then Error "invalid quote symbols"
  else match Paper_broker.credentials () with
  | Error _ as error -> error
  | Ok (key_id, secret) ->
    (* SOURCE: Alpaca's documented US crypto latest-quotes data endpoint.
       Only public market quotes are read; this is not a trading host. *)
    let encoded = List.map (fun result -> let symbol = Result.get_ok result in
      String.sub symbol 0 (String.length symbol - String.length "/USD") ^ "%2FUSD") canonical in
    let url = "https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes?symbols=" ^
      String.concat "%2C" (List.sort_uniq String.compare encoded) in
    Alpaca_http.get_json ~url ~key_id ~secret

let quote symbol = match canonical symbol with
  | Error _ as error -> error
  | Ok symbol -> match quote_document [symbol] with
    | Error _ as error -> error
    | Ok document -> parse_quote symbol document

let submitted_precision value =
  (* SOURCE: ledger quantities must equal the actual nine-decimal text sent
     to Alpaca, so binary representation cannot create phantom overfills. *)
  float_of_string (Printf.sprintf "%.9f" value)
let floor_increment value increment =
  (* SOURCE: move one representable value toward +infinity before flooring
     to avoid losing a whole increment to binary division at an exact grid. *)
  submitted_precision (floor (Float.next_after (value /. increment) infinity) *. increment)
let ceil_increment value increment =
  submitted_precision (ceil (Float.next_after (value /. increment) neg_infinity) *. increment)

let submit ?qty_text ?(market_exit=false) ~asset ~side ~qty ~limit_price ~client_order_id () =
  if Sys.getenv_opt "PAPER_ORDERS" <> Some "1" ||
     Sys.getenv_opt "MULTI_PAPER_ORDERS" <> Some "1" then
    Error "multi-market PAPER gates are not armed"
  else if side="buy" && not (allowed_entry asset.symbol) then
    Error "new crypto entries are restricted to BTC, ETH and SOL"
  else if market_exit && (side<>"sell" || allowed_entry asset.symbol) then
    Error "market wind-down is restricted to selling excluded crypto"
  else if not (String.starts_with ~prefix:"jsbotmtf" client_order_id) ||
          not (String.for_all (function 'a' .. 'z' | 'A' .. 'Z' | '0' .. '9' -> true | _ -> false)
            client_order_id) then Error "client order ID is outside multi-frame namespace"
  else if side <> "buy" && side <> "sell" ||
          not (Float.is_finite qty && Float.is_finite limit_price) ||
          qty < asset.minimum || limit_price <= 0. then Error "invalid crypto order fields"
  else match canonical asset.symbol, Alpaca_config.validate_base_url Paper_broker.base,
             Paper_broker.credentials () with
    | Error error, _, _ | _, Error error, _ | _, _, Error error -> Error error
    | Ok symbol, Ok (), Ok (key_id, secret) ->
      let quantity_text=Option.value ~default:(Printf.sprintf "%.9f" qty) qty_text in
      let exact=Exact_decimal.of_string quantity_text in
      if (match exact with Error _ -> true | Ok value ->
        value<=Exact_decimal.zero || Exact_decimal.to_float value<>qty ||
        (match Exact_decimal.of_string asset.step_text with
         | Error _ -> true | Ok step -> step<=Exact_decimal.zero || Int64.rem value step<>0L)) then
        Error "exact quantity does not match the owned request or asset grid"
      else let body = Yojson.Safe.to_string (`Assoc ([
        "symbol", `String symbol; "side", `String side;
        (* SOURCE: Alpaca crypto quantity supports at most nine decimal places. *)
        "qty", `String quantity_text;
        (* SOURCE: Alpaca supports market/limit crypto IOC; the user's removal
           instruction only gives market wind-down authority to excluded assets. *)
        "type", `String (if market_exit then "market" else "limit");
        "time_in_force", `String "ioc";
        "client_order_id", `String client_order_id ] @
        (if market_exit then [] else ["limit_price", `String (Printf.sprintf "%.9f" limit_price)]))) in
      Alpaca_http.post_json ~url:(Paper_broker.base ^ "/v2/orders") ~key_id ~secret ~body
