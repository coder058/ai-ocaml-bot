open Paper_market
(* Parity with the Python backtest on real S&P 500 closes, plus synthetic
   fail-closed checks. Prices here are fixtures, not market results. *)
let fail message=failwith message
let date_of n=let rec find y m d k=if k=0 then Printf.sprintf "%04d-%02d-%02d" y m d else
    let (y,m,d)=if d<Monthly_trend.days_in_month y m then (y,m,d+1) else if m=12 then (y+1,1,1) else (y,m+1,1) in
    find y m d (k-1) in find 2025 1 1 n
(* One synthetic bar per calendar day (no gaps) from 2025-01-01. *)
let synthetic count price=List.init count (fun i->{Monthly_trend.date=date_of i;close=price i})
let today=(2025,11,3)
let ()=
  let file=Sys.argv.(1) in
  let json=Yojson.Safe.from_file file in
  let bars=match Monthly_trend.bars_of_json (Option.get (Paper_broker.member "bars" json)) with
    | Ok bars->bars | Error e->fail e in
  let checked=ref 0 in
  (match Paper_broker.member "expected" json with
   | Some (`List rows)->List.iter (fun row->
       let text name=Option.get (Paper_broker.string (Paper_broker.member name row)) in
       let today=Option.get (Monthly_trend.parse_date (text "today")) in
       match Monthly_trend.decide ~today bars with
       | Error e->fail ("parity month rejected: " ^ e)
       | Ok r->
         if r.month<>text "month" then fail "parity decision month differs";
         if (r.decision=Monthly_trend.Hold)<>(Paper_broker.member "hold" row=Some (`Bool true)) then
           fail ("parity decision differs for " ^ r.month);
         incr checked) rows
   | _->fail "fixture has no expectations");
  if !checked<>24 then fail "expected 24 parity months";
  (* Rising series holds, falling series exits. *)
  let up=synthetic 305 (fun i->100.+.float_of_int i) and down=synthetic 305 (fun i->500.-.float_of_int i) in
  (match Monthly_trend.decide ~today up with Ok {decision=Hold;month="2025-10";_}->() | _->fail "rising series must hold");
  (match Monthly_trend.decide ~today down with Ok {decision=Flat;_}->() | _->fail "falling series must be flat");
  (* Current-month bars are ignored: a crash this month cannot leak into the decision. *)
  let crash=up @ [{Monthly_trend.date="2025-11-02";close=1.}] in
  (match Monthly_trend.decide ~today crash with Ok {decision=Hold;_}->() | _->fail "current-month bar leaked");
  let expect_error name bars=match Monthly_trend.decide ~today bars with Error _->() | Ok _->fail name in
  expect_error "stale month accepted" (List.filteri (fun i _->i<280) up);
  expect_error "short history accepted" (List.filteri (fun i _->i>150) up);
  expect_error "gap accepted" (List.filteri (fun i _->i<>200 && i<>201 && i<>202 && i<>203 && i<>204 && i<>205) up);
  expect_error "unordered accepted" (List.rev up);
  expect_error "nonpositive close accepted" (up @ [{Monthly_trend.date="2025-10-31";close=0.}]);
  expect_error "missing month end accepted" (List.filteri (fun i _->i<297) up);
  (* Intent verification recomputes the decision and binds the month. *)
  let reading=Result.get_ok (Monthly_trend.decide ~today up) in
  let cid=Monthly_trend.client_id ~symbol:"SPY" ~month:reading.month ~side:"buy" ~origin:"" in
  let intent side cid bars=`Assoc ["policy",`String Monthly_trend.policy;"symbol",`String "SPY";
    "side",`String side;"clientOrderId",`String cid;"bars",Monthly_trend.bars_to_json bars] in
  if Result.is_error (Monthly_trend.verify_intent ~today ~symbol:"SPY" ~side:"buy" ~client_id:cid (intent "buy" cid up)) then
    fail "valid trend intent rejected";
  if Result.is_ok (Monthly_trend.verify_intent ~today ~symbol:"SPY" ~side:"buy" ~client_id:cid (intent "buy" cid down)) then
    fail "buy accepted after the rule turned flat";
  if Result.is_ok (Monthly_trend.verify_intent ~today:(2025,12,1) ~symbol:"SPY" ~side:"buy" ~client_id:cid (intent "buy" cid up)) then
    fail "previous month's intent accepted in a new month";
  if Result.is_ok (Monthly_trend.verify_intent ~today ~symbol:"QQQ" ~side:"buy" ~client_id:cid (intent "buy" cid up)) then
    fail "intent symbol mismatch accepted";
  let exit_cid=Monthly_trend.client_id ~symbol:"SPY" ~month:"2025-10" ~side:"sell" ~origin:cid in
  let exit_intent=match intent "sell" exit_cid down with `Assoc f->`Assoc (("originEntryId",`String cid)::f) | j->j in
  if Result.is_error (Monthly_trend.verify_intent ~today ~symbol:"SPY" ~side:"sell" ~client_id:exit_cid exit_intent) then
    fail "valid trend exit rejected";
  if String.length cid<>40 || not (String.starts_with ~prefix:"aibotstk" cid) then fail "client ID outside router namespace";
  print_endline "monthly trend parity (24 real S&P 500 month ends) and fail-closed checks passed"
