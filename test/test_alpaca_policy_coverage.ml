open Paper_market
(* SOURCE: actual requested symbols are in the fixture. Prices, the clock and
   uniformly positive candidates are synthetic tests, not measured signals. *)
let now = 1790895900.
let strings key document=match Paper_broker.member key document with
  | Some (`List rows)->List.map (function `String s->s|_->failwith "invalid fixture symbol") rows
  | _->failwith "fixture universe absent"
let reading minutes=
  let start=int_of_float (now/.60.)/minutes*minutes-minutes in
  `Assoc ["status",`String "candidate";"candidate",`String "long";
    "trend",`String "rising";"candleShapes",`List [`String "hammer_shape"];
    "close",`Float 100.;"invalidationLevel",`Float 99.;
    "lastBarStart",`String (Multi_paper.stamp (float_of_int start*.60.));
    "orderAuthority",`Bool false;"winProbability",`Null]
let market venue symbol=`Assoc ["venue",`String venue;"symbol",`String symbol;
  "frames",`Assoc (List.map (fun (frame,minutes)->frame,reading minutes) Frame_analysis.frames)]
let ()=
  let fixture=Yojson.Safe.from_file Sys.argv.(1) in
  let stocks=strings "stocks" fixture and crypto=strings "crypto" fixture in
  let markets=List.map (market "Alpaca equities") stocks @ List.map (market "Alpaca crypto") crypto in
  let document=`Assoc ["policy",`String "trend_candle_confluence_v1";
    "asOf",`String (Multi_paper.stamp now);"retrievedAt",`String (Multi_paper.stamp now);
    "orderAuthority",`Bool false;"markets",`List markets] in
  let stock_signals=Result.get_ok (Stock_policy.signals ~now document) in
  let crypto_signals=Result.get_ok (Multi_paper.signals ~include_btc:true ~now document) in
  let frames=List.map fst Frame_analysis.frames in
  List.iter (fun symbol->List.iter (fun frame->
    if not (List.exists (fun (s:Stock_policy.signal)->s.symbol=symbol && s.frame=frame) stock_signals)
      then failwith ("stock/frame route missing: " ^ symbol ^ "/" ^ frame)) frames) stocks;
  List.iter (fun symbol->List.iter (fun frame->
    if not (List.exists (fun (s:Multi_paper.signal)->s.symbol=symbol && s.frame=frame) crypto_signals)
      then failwith ("crypto/frame route missing: " ^ symbol ^ "/" ^ frame)) frames) crypto;
  let expected=List.length markets * List.length frames in
  if List.length stock_signals+List.length crypto_signals<>expected then failwith "unexpected route count";
  Printf.printf "All %d requested Alpaca products / %d closed-frame policy routes accepted in synthetic pure-policy checks; no broker calls\n"
    (List.length markets) expected
