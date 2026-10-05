open Paper_market
open Fx_planning
(* SOURCE: all prices, clocks, IDs and catalog sizes here are SYNTHETIC
   adversarial fixtures, not observed FX data or strategy calibration. *)
let assoc fields = `Assoc fields
let replace key value = function `Assoc fields ->
  `Assoc ((key,value)::List.remove_assoc key fields) | _ -> assert false
let stamp = "2026-10-05T09:00:00.000000000Z"
let ns = Result.get_ok (Btc_quote_clock.source_ns stamp)
let account = assoc ["currency",`String "USD"]
let instrument name = assoc ["name",`String name;"type",`String "CURRENCY";
  "displayPrecision",`Int 5;"tradeUnitsPrecision",`Int 0;
  "minimumTradeSize",`String "1";"maximumOrderUnits",`String "1000000"]
let bucket price liquidity = assoc ["price",`String price;"liquidity",`Int liquidity]
let quote name bid ask = assoc ["instrument",`String name;"status",`String "tradeable";
  "time",`String stamp;"bids",`List [bucket bid 1000000];"asks",`List [bucket ask 1000000]]
let conversion currency value = assoc ["currency",`String currency;"positionValue",`String value]
let price q conversions = assoc ["prices",`List [q];"homeConversions",`List conversions;"time",`String stamp]
let q = quote "EUR_USD" "1.10000" "1.10010"
let pricing = price q [conversion "EUR" "1.10005";conversion "USD" "1"]
let prepare ?(a=account) ?(i=instrument "EUR_USD") ?(p=pricing)
    ?(side=Fx_order_plan.Buy) ?(budget="100") ?(bound="1.10020") ?(stop="1.09000")
    ?(id="aibotfxSynthetic") ?(now=ns) ?(received=ns) () =
  Fx_order_plan.prepare ~now_ns:now ~max_age_ns:1_000_000_000L ~received_ns:received
    ~account:a ~instrument:i ~pricing:p ~side ~budget_usd:budget
    ~price_bound:bound ~stop_price:stop ~client_id:id
let checks = ref 0
let check name passed = incr checks; if not passed then failwith name
let rejected name result = check name (Result.is_error result)
let field name row = Option.get (Paper_broker.member name row)
let () =
  let plan = Result.get_ok (prepare ()) in
  check "EUR dollar budget is converted to base units, never 100 dollars as 100 EUR"
    (plan.units="90" && plan.valuation_unit_usd="1.1002");
  let order = field "order" plan.request in
  List.iter (fun (name,value) -> check ("request "^name) (field name order=`String value))
    ["type","MARKET";"timeInForce","FOK";"positionFill","OPEN_ONLY";
     "units","90";"instrument","EUR_USD";"priceBound","1.1002"];
  check "stop is caller-supplied and attached to broker request"
    (field "price" (field "stopLossOnFill" order)=`String "1.09");
  check "trade identity retains exact owned namespace"
    (field "id" (field "tradeClientExtensions" order)=`String "aibotfxSynthetic");
  check "source and reception evidence preserved" (plan.quote_time=stamp && plan.received_ns=ns);
  check "50 tier" ((Result.get_ok (prepare ~budget:"50" ())).units="45");
  check "500 tier" ((Result.get_ok (prepare ~budget:"500" ())).units="454");
  check "unit precision floors rather than rounds up"
    ((Result.get_ok (prepare ~i:(replace "tradeUnitsPrecision" (`Int 2) (instrument "EUR_USD")) ())).units="90.89");
  let jq = quote "USD_JPY" "150.000" "150.010" in
  check "USD JPY uses USD base units, not division by yen quote"
    ((Result.get_ok (prepare ~i:(replace "displayPrecision" (`Int 3) (instrument "USD_JPY"))
       ~p:(price jq [conversion "USD" "1";conversion "JPY" "0.006666667"])
       ~bound:"150.020" ~stop:"149.000" ())).units="100");
  let eq = quote "EUR_GBP" "0.80000" "0.80010" in
  check "cross pair uses measured USD conversion and signed base units"
    ((Result.get_ok (prepare ~i:(instrument "EUR_GBP")
       ~p:(price eq [conversion "EUR" "1.20000";conversion "GBP" "1.50000"])
       ~side:Fx_order_plan.Sell ~bound:"0.79990" ~stop:"0.81000" ())).units="-83");
  List.iter (fun budget -> rejected ("invalid tier "^budget) (prepare ~budget ()))
    ["30";"0";"501";"100.000000001";"NaN";"1e2";"-100"];
  rejected "wrong home currency cannot silently size in dollars"
    (prepare ~a:(replace "currency" (`String "EUR") account) ());
  rejected "MT4 account cannot carry client extensions"
    (prepare ~a:(replace "mt4AccountID" (`Int 1) account) ());
  rejected "duplicate account currency" (prepare ~a:(assoc ["currency",`String "USD";"currency",`String "EUR"]) ());
  rejected "foreign client namespace" (prepare ~id:"otherBot" ());
  rejected "injected client ID" (prepare ~id:"aibotfx/bad" ());
  rejected "ETF does not become spot FX" (prepare ~i:(replace "type" (`String "CFD") (instrument "EUR_USD")) ());
  rejected "not a conventional pair" (prepare ~i:(instrument "xyz:EUR") ());
  rejected "same currency pair" (prepare ~i:(instrument "USD_USD") ());
  rejected "excess catalog precision" (prepare ~i:(replace "tradeUnitsPrecision" (`Int 10) (instrument "EUR_USD")) ());
  rejected "minimum order not reachable" (prepare ~i:(replace "minimumTradeSize" (`String "100") (instrument "EUR_USD")) ());
  rejected "maximum order exceeded" (prepare ~i:(replace "maximumOrderUnits" (`String "80") (instrument "EUR_USD")) ());
  rejected "top price has insufficient actual liquidity"
    (prepare ~p:(price (replace "asks" (`List [bucket "1.10010" 80]) q) [conversion "EUR" "1.10005"]) ());
  rejected "missing conversion" (prepare ~p:(price q [conversion "GBP" "1"]) ());
  rejected "duplicate conversion" (prepare ~p:(price q [conversion "EUR" "1";conversion "EUR" "2"]) ());
  rejected "conversion precision never silently truncates divisor"
    (prepare ~p:(price q [conversion "EUR" "1.1000000001"]) ());
  rejected "conversion overflow" (prepare ~p:(price q [conversion "EUR" "99999999999"]) ());
  rejected "duplicate quote" (prepare ~p:(replace "prices" (`List [q;q]) pricing) ());
  rejected "non tradeable quote" (prepare ~p:(price (replace "status" (`String "non-tradeable") q) [conversion "EUR" "1"]) ());
  rejected "conflicting tradeable flag" (prepare ~p:(price (replace "tradeable" (`Bool false) q) [conversion "EUR" "1"]) ());
  rejected "crossed quote" (prepare ~p:(price (quote "EUR_USD" "1.2" "1.1") [conversion "EUR" "1.1"]) ());
  rejected "stale source" (prepare ~now:(Int64.add ns 1_000_000_001L) ~received:(Int64.add ns 1_000_000_001L) ());
  rejected "one ns future quote" (prepare ~now:(Int64.sub ns 1L) ());
  rejected "one ns future receipt" (prepare ~received:(Int64.add ns 1L) ());
  rejected "pricing poll precedes actual quote"
    (prepare ~p:(replace "time" (`String "2026-10-05T08:59:59.999999999Z") pricing) ());
  rejected "invalid calendar" (prepare ~p:(replace "time" (`String "2026-02-30T09:00:00Z") pricing) ());
  rejected "buy bound below ask" (prepare ~bound:"1.1" ());
  rejected "long stop inside spread" (prepare ~stop:"1.10005" ());
  rejected "short bound above bid" (prepare ~side:Fx_order_plan.Sell ~bound:"1.1001" ~stop:"1.2" ());
  rejected "short stop inside spread" (prepare ~side:Fx_order_plan.Sell ~bound:"1.0999" ~stop:"1.10005" ());
  rejected "price exceeds provider precision" (prepare ~bound:"1.100201" ());
  (* SOURCE: exact integer arithmetic for these bounded fixture products checks
     that flooring every supported grid cannot enlarge snapshot allocation. *)
  List.iter (fun digits -> List.iter (fun budget ->
    let plan = Result.get_ok (prepare ~budget ~i:(replace "tradeUnitsPrecision" (`Int digits) (instrument "EUR_USD")) ()) in
    let units = Result.get_ok (Exact_decimal.of_string plan.units) in
    let factor = Result.get_ok (Exact_decimal.of_string plan.valuation_unit_usd) in
    let budget = Result.get_ok (Exact_decimal.of_string budget) in
    check "exact snapshot unit valuation stays within tier"
      (Int64.rem factor 10_000L=0L &&
       Int64.mul units (Int64.div factor 10_000L) <= Int64.mul budget 100_000L)
  ) ["50";"100";"500"]) [0;1;2;3;4;5;6;7;8;9];
  Printf.printf "%d synthetic FX request-planning checks passed; no broker calls\n" !checks
