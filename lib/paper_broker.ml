(* Narrow Alpaca PAPER crypto adapter. There is no configurable trading host. *)

let base = Alpaca_config.paper_base_url
let symbol = "BTC/USD"

let member name = function
  | `Assoc fields -> List.assoc_opt name fields
  | _ -> None

let string = function Some (`String s) -> Some s | _ -> None
let bool = function Some (`Bool b) -> Some b | _ -> None
let float = function
  | Some (`String s) -> (try Some (float_of_string s) with _ -> None)
  | Some (`Float f) -> Some f
  | Some (`Int i) -> Some (float_of_int i)
  | _ -> None

let credentials () =
  match Alpaca_config.api_key_id (), Alpaca_config.api_secret_key () with
  | Some key_id, Some secret -> Ok (key_id, secret)
  | _ -> Error "Alpaca PAPER credentials are absent"

let get path =
  match Alpaca_config.validate_base_url base, credentials () with
  | Error e, _ | _, Error e -> Error e
  | Ok (), Ok (key_id, secret) ->
    Alpaca_http.get_json ~url:(base ^ path) ~key_id ~secret

let account () =
  match get "/v2/account" with
  | Error e -> Error e
  | Ok j ->
    (match string (member "status" j), bool (member "trading_blocked" j),
           float (member "non_marginable_buying_power" j) with
     | Some status, Some blocked, Some power when Float.is_finite power ->
       (match string (member "crypto_status" j) with
        | Some crypto_status
          when not (List.mem crypto_status [ "ACTIVE"; "PAPER_ONLY" ]) ->
          Error ("crypto account not active: " ^ crypto_status)
        | _ -> Ok (status, blocked, power))
     | _ -> Error "account fields missing")

let positions () =
  match get "/v2/positions" with
  | Error e -> Error e
  | Ok (`List items) ->
    let matches j =
      match string (member "symbol" j) with
      | Some ("BTCUSD" | "BTC/USD") -> true
      | _ -> false
    in
    let matches = List.filter matches items in
    (match matches with
     | [] -> Ok 0.
     | [ p ] ->
       (match float (member "qty" p) with
        | Some q when Float.is_finite q && q >= 0. -> Ok q
        | _ -> Error "invalid BTC position")
     | _ -> Error "multiple BTC positions")
  | Ok _ -> Error "positions response was not an array"

let any_open_order () =
  match get "/v2/orders?status=open" with
  | Ok (`List items) -> Ok (items <> [])
  | Ok _ -> Error "open orders response was not an array"
  | Error e -> Error e

let price_increment () =
  match get "/v2/assets/BTCUSD" with
  | Error e -> Error e
  | Ok j ->
    (match bool (member "tradable" j), float (member "price_increment" j) with
     | Some true, Some tick when Float.is_finite tick && tick > 0. -> Ok tick
     | _ -> Error "BTC asset not tradable or price increment unavailable")

let order_by_client_id id =
  get ("/v2/orders:by_client_order_id?client_order_id=" ^ id)

let submit_ioc ~side ~qty ~limit_price ~client_order_id =
  if Sys.getenv_opt "PAPER_ORDERS" <> Some "1" then
    Error "PAPER_ORDERS gate is not armed"
  else match Alpaca_config.validate_base_url base, credentials () with
  | Error e, _ | _, Error e -> Error e
  | Ok (), Ok (key_id, secret) ->
    if (side <> "buy" && side <> "sell") || qty <= 0. ||
       not (Float.is_finite qty) || limit_price <= 0. ||
       not (Float.is_finite limit_price) then Error "invalid order fields"
    else
      let body = Yojson.Safe.to_string (`Assoc [
        "symbol", `String symbol;
        (* # SOURCE: Alpaca crypto quantity precision is at most nine decimals. *)
        "qty", `String (Printf.sprintf "%.9f" qty);
        "side", `String side;
        "type", `String "limit";
        "time_in_force", `String "ioc";
        "limit_price", `String (string_of_float limit_price);
        "client_order_id", `String client_order_id;
      ]) in
      Alpaca_http.post_json ~url:(base ^ "/v2/orders") ~key_id ~secret ~body

let order_status j = string (member "status" j)
