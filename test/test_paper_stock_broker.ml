open Paper_market
let ok = function Ok value -> value | Error text -> failwith text
let check text passed = if not passed then failwith text
let () =
  assert (Result.is_error (Paper_stock_broker.symbol "BTCUSD"));
  (* SOURCE: synthetic payload fixtures validate routing, not broker fills. *)
  let asset=Paper_stock_broker.{symbol="QQQ";fractionable=true} in
  let id="aibotstkfixture" in
  let buy=ok (Paper_stock_broker.body ~asset ~side:"buy" ~amount:"100" ~client_order_id:id)
    |> Yojson.Safe.from_string in
  check "fractional buy uses notional DAY" (Paper_broker.string (Paper_broker.member "notional" buy)=Some "100.000000000" &&
    Paper_broker.member "qty" buy=None && Paper_broker.string (Paper_broker.member "time_in_force" buy)=Some "day");
  let sell=ok (Paper_stock_broker.body ~asset ~side:"sell" ~amount:"0.123456789" ~client_order_id:id)
    |> Yojson.Safe.from_string in
  check "sell retains exact quantity" (Paper_broker.string (Paper_broker.member "qty" sell)=Some "0.123456789" &&
    Paper_broker.member "notional" sell=None);
  check "AAPL protected" (Result.is_error (Paper_stock_broker.symbol "AAPL"));
  check "crypto cannot become stock" (Result.is_error (Paper_stock_broker.symbol "ETH/USD"));
  check "URL injection blocked" (Result.is_error (Paper_stock_broker.symbol "QQQ?x=1"));
  check "notional cap enforced" (Result.is_error (Paper_stock_broker.body ~asset ~side:"buy" ~amount:"500.01" ~client_order_id:id));
  check "unowned namespace blocked" (Result.is_error (Paper_stock_broker.body ~asset ~side:"buy" ~amount:"100" ~client_order_id:"external"));
  print_endline "stock paper routing checks passed"
