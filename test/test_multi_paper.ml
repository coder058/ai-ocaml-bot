open Paper_market
let failures = ref 0
let check name passed = Printf.printf "%s %s\n" (if passed then "ok" else "FAIL") name;
  if not passed then incr failures
(* SOURCE: all prices, dates, quantities and portfolio counts in this test are
   SYNTHETIC fixtures. They are not market observations or strategy evidence. *)
let now = 1790895900.
let minute = int_of_float (now /. 60.)
let bar = Multi_paper.stamp (float_of_int (minute - 5) *. 60.)
let reading = `Assoc ["status",`String "candidate"; "candidate",`String "long";
  "lastBarStart",`String bar; "invalidationLevel",`Float 90.; "close",`Float 100.;
  "orderAuthority",`Bool false; "winProbability",`Null]
let market symbol = `Assoc ["symbol",`String symbol; "venue",`String "Alpaca crypto";
  "frames",`Assoc ["5m",reading]]
let document = `Assoc ["asOf",`String (Multi_paper.stamp now);
  "policy",`String "trend_candle_confluence_v1"; "orderAuthority",`Bool false;
  "markets",`List [market "ETH/USD";market "BTC/USD"]]
let signal : Multi_paper.signal = {symbol="ETH/USD"; frame="5m"; bar; stop=90.;reading}
let order pending status qty price = `Assoc [
  "client_order_id",`String pending.Multi_paper.client_id; "symbol",`String "ETHUSD";
  "side",`String pending.side; "status",`String status; "filled_qty",`String qty;
  "filled_avg_price",(match price with None -> `Null | Some p -> `String p)]
let change name value = function `Assoc fields -> `Assoc ((name,value)::List.remove_assoc name fields)
  | value -> value
let () =
  check "measured event precision preserves canonical candle boundaries"
    (Multi_paper.stamp 0. = "1970-01-01T00:00:00Z" &&
     Multi_paper.observed_stamp 0. = "1970-01-01T00:00:00.000000Z" &&
     Multi_paper.observed_stamp 0.125 = "1970-01-01T00:00:00.125000Z" &&
     Multi_paper.observed_stamp 59.99999975 = "1970-01-01T00:00:59.999999Z" &&
     Multi_paper.observed_stamp 60. = "1970-01-01T00:01:00.000000Z" &&
     Multi_paper.observed_stamp (-0.125) = "1969-12-31T23:59:59.875000Z");
  check "canonical crypto rejects equities/URL injection"
    (Paper_crypto_broker.canonical "ETHUSD"=Ok "ETH/USD" &&
     Result.is_error (Paper_crypto_broker.canonical "AAPL") &&
     Result.is_error (Paper_crypto_broker.canonical "ETH/USD?x=1") &&
     Result.is_error (Paper_crypto_broker.canonical "ETH//USD"));
  check "fresh closed signal accepted and legacy BTC excluded"
    (match Multi_paper.signals ~now document with Ok [s] -> s.symbol="ETH/USD" | _ -> false);
  check "explicit handoff policy includes BTC without changing default authority"
    (match Multi_paper.signals ~include_btc:true ~now document with
      | Ok signals -> List.map (fun (s:Multi_paper.signal)->s.symbol) signals=["ETH/USD";"BTC/USD"]
      | _ -> false);
  check "crypto entry universe excludes altcoins"
    (Paper_crypto_broker.allowed_entry "BTCUSD" && Paper_crypto_broker.allowed_entry "ETH/USD" &&
     Paper_crypto_broker.allowed_entry "SOL/USD" && not (Paper_crypto_broker.allowed_entry "BONK/USD") &&
     not (Paper_crypto_broker.allowed_entry "PEPEUSD"));
  check "altcoin candle signals cannot gain entry authority"
    (match Multi_paper.signals ~now (change "markets" (`List [market "BONK/USD";market "PEPE/USD"]) document)
     with Ok [] -> true | _ -> false);
  check "stale/future snapshots rejected"
    (Result.is_error (Multi_paper.signals ~now:(now +. 180.) document) &&
     Result.is_error (Multi_paper.signals ~now:(now -. 60.) document));
  check "no order probability invented"
    (Multi_paper.signals ~now (change "markets" (`List [change "frames"
      (`Assoc ["5m",change "winProbability" (`Float 0.9) reading]) (market "ETH/USD")]) document)=Ok []);
  let state,ticket = Multi_paper.entry Multi_paper.empty signal ~now ~qty:1. ~price:100. in
  let btc_state,_ = Multi_paper.entry Multi_paper.empty {signal with symbol="BTC/USD"} ~now ~qty:1. ~price:100. in
  check "BTC handoff ownership survives durable state recovery"
    (Multi_paper.of_json (Multi_paper.to_json btc_state)=Ok btc_state);
  check "one owned ticket prevents contradictory frames"
    (not (Multi_paper.eligible state {signal with frame="1h"}));
  check "entry identifier deterministic"
    (ticket.entry_id=(snd (Multi_paper.entry Multi_paper.empty signal ~now ~qty:1. ~price:100.)).entry_id);
  check "durable state round-trips before POST" (Multi_paper.of_json (Multi_paper.to_json state)=Ok state);
  let pending=Option.get ticket.pending in
  let partial=Multi_paper.reconcile ticket (order pending "canceled" "0.4" (Some "100")) in
  check "partially filled canceled entry owns only actual fill"
    (match partial with Ok t -> t.owned_max=0.4 && not t.closed && t.pending=None | _ -> false);
  check "uncertain/nonfinal outcome keeps same pending ID"
    (Multi_paper.reconcile ticket (order pending "new" "0" None)=Ok ticket);
  check "wrong client ID cannot alter ownership"
    (Result.is_error (Multi_paper.reconcile ticket (change "client_order_id" (`String "foreign")
       (order pending "filled" "1" (Some "100")))));
  check "overfill cannot create ownership"
    (Result.is_error (Multi_paper.reconcile ticket (order pending "filled" "2" (Some "100"))));
  let rejected=Multi_paper.reconcile ticket (order pending "rejected" "0" None) in
  check "rejected entry closes without position"
    (match rejected with Ok t -> t.closed && t.owned_max=0. | _ -> false);
  let owned=Result.get_ok partial in
  let state=Multi_paper.replace_ticket state owned in
  let state,selling=Multi_paper.exit state owned ~now ~qty:0.3 ~price:99.
    ~quote_time:"synthetic-quote" ~reason:"synthetic exit" in
  let selling_pending=Option.get selling.pending in
  let sold=Multi_paper.reconcile selling (order selling_pending "canceled" "0.2" (Some "99")) in
  check "partial exit retains remaining owned inventory"
    (match sold with Ok t -> t.owned_max=0.2 && t.exit_filled=0.2 && not t.closed | _ -> false);
  check "seen bar prevents immediate reentry when ticket closes"
    (not (Multi_paper.eligible (Multi_paper.replace_ticket state {owned with closed=true}) signal));
  let quote : Paper_crypto_broker.quote = {timestamp=Multi_paper.stamp now;
    minute; seconds=0.; bid=89.; ask=90.} in
  check "invalidation exit uses actual entry candle low"
    (Multi_paper.exit_reason ~now owned quote document <> None);
  check "stale and future quote blocked"
    (Multi_paper.quote_fresh ~now quote && not (Multi_paper.quote_fresh ~now:(now+.10.) quote) &&
     not (Multi_paper.quote_fresh ~now:(now-.1.) quote));
  let duplicate = Multi_paper.to_json {state with tickets=[owned;owned]} in
  check "duplicate ledger symbols halt instead of guessing" (Result.is_error (Multi_paper.of_json duplicate));
  if !failures > 0 then exit 1
