open Paper_market
let fail message=failwith message
let with_env value f=Unix.putenv "ALLOW_NEGATIVE_EDGE_POLICY" value;f ()
let ()=
  with_env "" (fun ()->
    if Loss_guard.allows Loss_guard.quote_cross || Loss_guard.allows Loss_guard.candle_confluence then
      fail "empty acknowledgement allowed a negative-edge policy");
  with_env "quote_cross_30s_v1" (fun ()->
    if not (Loss_guard.allows Loss_guard.quote_cross) then fail "named policy not allowed";
    if Loss_guard.allows Loss_guard.candle_confluence then fail "unnamed policy allowed");
  with_env " trend_candle_confluence_v1 , quote_cross_30s_v1" (fun ()->
    if not (Loss_guard.allows Loss_guard.quote_cross && Loss_guard.allows Loss_guard.candle_confluence) then
      fail "comma list not parsed");
  with_env "quote_cross" (fun ()->if Loss_guard.allows Loss_guard.quote_cross then fail "prefix accepted");
  print_endline "loss guard acknowledgement checks passed"
