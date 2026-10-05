open Paper_market
let check name condition=if not condition then failwith name
let unwrap=function Ok value->value | Error message->failwith message
(* SOURCE: synthetic UTC timestamps/nanoseconds test strict calendar,
   precision and inherited five-second guard; no market latency claim. *)
let () =
  let stamp="2026-10-05T00:00:01.000000001Z" in
  let source=unwrap (Btc_quote_clock.source_ns stamp) in
  check "nanosecond preserved" (Int64.sub source (unwrap (Btc_quote_clock.source_ns "2026-10-05T00:00:01Z"))=1L);
  let limit=5_000_000_000L in
  let run ?(receipt=Some source) now text=Btc_quote_clock.validate
    ~now_ns:now ~max_age_ns:limit ~received_ns:receipt ~timestamp:text in
  check "exact guard boundary admitted" (Result.is_ok (run (Int64.add source limit) stamp));
  check "one ns stale rejected" (Result.is_error (run (Int64.add source (Int64.succ limit)) stamp));
  check "future source rejected" (Result.is_error (run (Int64.pred source) stamp));
  check "source after receipt rejected" (Result.is_error (run ~receipt:(Some (Int64.pred source)) source stamp));
  check "future receipt rejected" (Result.is_error (run ~receipt:(Some (Int64.succ source)) source stamp));
  check "stale receipt rejected" (Result.is_error (run ~receipt:(Some (Int64.sub source (Int64.succ limit))) source stamp));
  check "REST source still checked without receipt" (Result.is_error (run ~receipt:None (Int64.add source (Int64.succ limit)) stamp));
  List.iter (fun text -> check "invalid source timestamp rejected" (Result.is_error (Btc_quote_clock.source_ns text)))
    ["2026-02-30T00:00:00Z";"2026-10-05T00:00:60Z";"2026-10-05T00:00:01.Z";
     "2026-10-05T00:00:01.0000000001Z";"2026-10-05T00:00:01+00:00";
     "2026-+1-05T00:00:01Z";"2026-10-05T+0:00:01Z";
     "2026-10-05T00:00X01Z";
     "2026-10-05T00:00:01e0Z";"9999-10-05T00:00:01Z";"" ];
  print_endline "BTC source/receipt exact quote clock checks passed"
