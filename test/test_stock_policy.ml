open Paper_market
(* SOURCE: synthetic prices/times exercise causal routing, not market results. *)
let fail message=failwith message
let now=1760013000.
let as_of=Multi_paper.stamp now
let bar=Multi_paper.stamp (now-.60.)
let reading=`Assoc ["status",`String "candidate";"candidate",`String "long";
  "trend",`String "rising";"candleShapes",`List [`String "hammer_shape"];
  "lastBarStart",`String bar;"close",`Float 100.;"invalidationLevel",`Float 99.;
  "orderAuthority",`Bool false;"winProbability",`Null]
let document venue symbol r=`Assoc ["policy",`String "trend_candle_confluence_v1";
  "asOf",`String as_of;"retrievedAt",`String as_of;"orderAuthority",`Bool false;
  "markets",`List [`Assoc ["venue",`String venue;"symbol",`String symbol;
    "frames",`Assoc ["1m",r]]]]
let replace name value=function `Assoc fields->`Assoc ((name,value)::List.remove_assoc name fields)|_->assert false
let count d=match Stock_policy.signals ~now d with Ok signals->List.length signals|Error _-> -1
let ()=
  if count (document "Alpaca equities" "QQQ" reading)<>1 then fail "valid stock close rejected";
  if count (document "Alpaca equities" "AAPL" reading)<>0 then fail "AAPL allowed";
  if count (document "Hyperliquid HIP-3" "xyz:QQQ" reading)<>0 then fail "HIP-3 routed";
  if count (document "Alpaca crypto" "ETH/USD" reading)<>0 then fail "crypto routed";
  List.iter (fun r->if count (document "Alpaca equities" "QQQ" r)<>0 then fail "invalid signal allowed")
    [replace "candidate" (`String "short") reading;replace "lastBarStart" (`String as_of) reading;
     replace "lastBarStart" (`String (Multi_paper.stamp (now-.120.))) reading;
     replace "status" (`String "market_closed") reading;replace "invalidationLevel" (`Float 101.) reading;
     replace "winProbability" (`Float 0.9) reading;replace "trend" (`String "falling") reading;
     replace "candleShapes" (`List []) reading];
  if count (replace "retrievedAt" (`String (Multi_paper.stamp (now+.60.))) (document "Alpaca equities" "QQQ" reading))<> -1 then fail "future snapshot allowed";
  List.iter (fun (frame,minutes)->
    let start=int_of_float (now/.60.)/minutes*minutes-minutes in
    let r=replace "lastBarStart" (`String (Multi_paper.stamp (float_of_int start*.60.))) reading in
    let d=document "Alpaca equities" "QQQ" r in
    let market=`Assoc ["symbol",`String "QQQ";"venue",`String "Alpaca equities";"frames",`Assoc [frame,r]] in
    if count (replace "markets" (`List [market]) d)<>1 then fail ("closed frame rejected: " ^ frame)
  ) Frame_analysis.frames;
  let quote t=`Assoc ["quotes",`Assoc ["QQQ",`Assoc ["t",`String t;"bp",`Float 99.;"ap",`Float 100.]]] in
  (match Stock_policy.quote ~now ~symbol:"QQQ" (quote as_of) with Ok _->()|Error error->fail error);
  (match Stock_policy.quote ~now ~symbol:"QQQ" (quote (Multi_paper.stamp (now-.60.))) with Error _->()|Ok _->fail "old quote allowed");
  print_endline "stock policy causal routing checks passed"
