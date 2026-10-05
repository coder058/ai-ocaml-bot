(* Current stock router's final submission boundary. Keep the frozen analysis
   library unchanged; delegate its existing gates, session, body and origin
   validation, then check recorded evidence immediately before HTTP POST. *)
open Paper_market

let submit ~pre_submit ~asset ~side ~amount ~client_order_id =
  let ready =
    if Sys.getenv_opt "PAPER_ORDERS"<>Some "1" || Sys.getenv_opt "STOCK_PAPER_ORDERS"<>Some "1" then
      Error "stock paper execution gates are not armed"
    else Result.bind (Paper_stock_broker.session_open ()) (fun () ->
      Result.bind (Paper_stock_broker.body ~asset ~side ~amount ~client_order_id) (fun body ->
        Result.bind (Alpaca_config.validate_base_url Paper_broker.base) (fun () ->
          Result.map (fun credentials -> body,credentials) (Paper_broker.credentials ())))) in
  (* SOURCE: no order POST has occurred before these validations. Preserve the
     distinction between certain non-submission and uncertain HTTP outcomes. *)
  match ready with
  | Error reason -> Error (`Not_sent reason)
  | Ok (body,(key_id,secret)) ->
    match pre_submit () with
    | Error reason -> Error (`Not_sent reason)
    | Ok () ->
      Result.map_error (fun error -> `Broker error)
        (Alpaca_http.post_json ~url:(Paper_broker.base ^ "/v2/orders") ~key_id ~secret ~body)
