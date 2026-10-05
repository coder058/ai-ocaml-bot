(* Pure request preparation, not an execution adapter or a strategy.
   SOURCE: https://developer.oanda.com/rest-live-v20/order-df/
   SOURCE: https://developer.oanda.com/rest-live-v20/pricing-df/
   SOURCE: https://developer.oanda.com/rest-live-v20/pricing-ep/
   No float-to-units conversion, network call, credential or guessed FX rate. *)
open Paper_market
type side = Buy | Sell
type t = {
  request : Yojson.Safe.t; units : string; budget_usd : string;
  valuation_unit_usd : string; quote_time : string;
  conversion_poll_time : string; received_ns : int64;
}
let ( let* ) = Result.bind
let object_fields = function
  | `Assoc fields when List.length fields =
      List.length (List.sort_uniq String.compare (List.map fst fields)) -> Ok fields
  | _ -> Error "FX object is missing or has duplicate fields"
let required fields key = match List.assoc_opt key fields with
  | Some value -> Ok value | None -> Error ("FX field missing: " ^ key)
let text = function `String value -> Ok value | _ -> Error "FX text field is invalid"
let text_field fields key = let* value = required fields key in text value
let list = function `List rows -> Ok rows | _ -> Error "FX list field is invalid"
let list_field fields key = let* value = required fields key in list value
let precision = function
  (* SOURCE: existing Exact_decimal stores nine fractional digits. Unsupported
     provider precision is rejected, never silently truncated for a divisor. *)
  | `Int value when value >= 0 && value <= Exact_decimal.digits -> Ok value
  | _ -> Error "FX precision exceeds supported exact arithmetic"
let fraction_digits text =
  match String.split_on_char '.' text with
  | [_] -> 0
  | [_; fraction] ->
    let rec trim n = if n > 0 && fraction.[n-1]='0' then trim (n-1) else n in
    trim (String.length fraction)
  | _ -> Exact_decimal.digits + 1
let decimal ?(digits=Exact_decimal.digits) value =
  let* text = text value in
  if fraction_digits text > digits then Error "FX decimal precision would be lost"
  else let* value = Exact_decimal.of_string text in
    if value <= Exact_decimal.zero then Error "FX decimal must be positive" else Ok value
let decimal_field fields key = let* value = required fields key in decimal value
let compact value =
  let text = Exact_decimal.to_string value in
  let rec trim n = if n > 0 && text.[n-1]='0' then trim (n-1) else n in
  let n = trim (String.length text) in
  String.sub text 0 (if text.[n-1]='.' then n-1 else n)
let unique_named ~key ~name rows =
  let rec find matches = function
    | [] -> (match matches with [fields] -> Ok fields
      | _ -> Error "FX provider identity is absent or duplicated")
    | row::rest -> let* fields = object_fields row in
      let* actual = text_field fields key in
      find (if actual=name then fields::matches else matches) rest in
  find [] rows
let pair name = match String.split_on_char '_' name with
  | [base;quote] when base<>quote && List.for_all (fun currency ->
      (* SOURCE: OANDA conventional FX instrument names use two ISO currency
         codes. Account-specific CURRENCY membership is also required below. *)
      String.length currency=3 && String.for_all (function 'A'..'Z'->true|_->false) currency)
      [base;quote] -> Ok (base,quote)
  | _ -> Error "FX instrument is not a conventional currency pair"
let top_bucket rows ~digits = match rows with
  | first::_ -> let* fields = object_fields first in
    let* price = required fields "price" in let* price = decimal ~digits price in
    let* liquidity = required fields "liquidity" in
    let* liquidity = (match liquidity with
      | `Int n when n>0 -> decimal (`String (string_of_int n))
      | `Intlit n -> decimal (`String n)
      | _ -> Error "FX top-price liquidity is invalid") in
    Ok (price,liquidity)
  | [] -> Error "FX executable price buckets are missing"
let prepare ~now_ns ~max_age_ns ~received_ns ~account ~instrument ~pricing
    ~side ~budget_usd ~price_bound ~stop_price ~client_id =
  let* account = object_fields account in
  let* currency = text_field account "currency" in
  if currency<>"USD" then Error "FX initial planner requires USD account home currency"
  else if List.assoc_opt "mt4AccountID" account<>None &&
          List.assoc_opt "mt4AccountID" account<>Some `Null then
    Error "MT4 account cannot use owned client extensions"
  else if not (String.starts_with ~prefix:"aibotfx" client_id) ||
          client_id="aibotfx" || not (String.for_all (function
            'a'..'z'|'A'..'Z'|'0'..'9'->true|_->false) client_id) then
    Error "FX client ID is outside the owned namespace"
  else let* asset = object_fields instrument in
    let* name = text_field asset "name" in
    let* base,quote_currency = pair name in
    let* kind = text_field asset "type" in
    if kind<>"CURRENCY" then Error "FX account instrument is not CURRENCY"
    else let* p = required asset "displayPrecision" in let* p = precision p in
      let* u = required asset "tradeUnitsPrecision" in let* u = precision u in
      let* minimum = decimal_field asset "minimumTradeSize" in
      let* maximum = decimal_field asset "maximumOrderUnits" in
      if minimum>maximum then Error "FX instrument size bounds are contradictory"
      else let* budget = decimal (`String budget_usd) in
        (* SOURCE: user's requested dollar tiers. They are allocation requests,
           not calibrated confidence/probability or maximum-loss estimates. *)
        if not (List.mem budget (List.map (fun n -> Int64.mul n Exact_decimal.scale)
              [50L;100L;500L])) then Error "FX budget is outside the user dollar tiers"
        else let* pricing = object_fields pricing in
          let* prices = list_field pricing "prices" in
          let* price = unique_named ~key:"instrument" ~name prices in
          let* status = text_field price "status" in
          if status<>"tradeable" || (match List.assoc_opt "tradeable" price with
            | None | Some (`Bool true) -> false | _ -> true) then
            Error "FX quote is not tradeable"
          else let* quote_time = text_field price "time" in
            let* _ = Btc_quote_clock.validate ~now_ns ~max_age_ns
                ~received_ns:(Some received_ns) ~timestamp:quote_time in
            let* conversion_poll_time = text_field pricing "time" in
            let* _ = Btc_quote_clock.validate ~now_ns ~max_age_ns
                ~received_ns:(Some received_ns) ~timestamp:conversion_poll_time in
            let* q_ns = Btc_quote_clock.source_ns quote_time in
            let* poll_ns = Btc_quote_clock.source_ns conversion_poll_time in
            if q_ns>poll_ns then Error "FX quote is later than the pricing poll"
            else let* bids = list_field price "bids" in
              let* asks = list_field price "asks" in
              let* bid,bid_liquidity = top_bucket bids ~digits:p in
              let* ask,ask_liquidity = top_bucket asks ~digits:p in
              if bid>ask then Error "FX bid/ask is crossed"
              else let* bound = decimal ~digits:p (`String price_bound) in
                let* stop = decimal ~digits:p (`String stop_price) in
                if (match side with Buy -> bound<ask || stop>=bid
                  | Sell -> bound>bid || stop<=ask) then
                  Error "FX price bound or protective stop is on the wrong side"
                else let* conversions = list_field pricing "homeConversions" in
                  let* conversion = unique_named ~key:"currency" ~name:base conversions in
                  let* factor = decimal_field conversion "positionValue" in
                  if base="USD" && factor<>Exact_decimal.scale then
                    Error "FX USD home conversion is inconsistent"
                  else
                    (* SOURCE: HomeConversions.positionValue converts base units
                       to home USD. For USD-quoted pairs also include the worse
                       observed ask/buy bound. Cross-pair conversion can move;
                       this is a snapshot valuation, NOT a guaranteed fill cap. *)
                    let factor = if quote_currency="USD" then
                        max factor (match side with Buy -> bound | Sell -> ask)
                      else factor in
                    let* units = Exact_decimal.ratio budget factor in
                    (* SOURCE: decimal order grid follows the account catalog's
                       tradeUnitsPrecision within the nine-digit representation. *)
                    let rec power n = if n=0 then 1L else Int64.mul 10L (power (n-1)) in
                    let grid = power (Exact_decimal.digits-u) in
                    let* units = Exact_decimal.floor_grid units grid in
                    let liquidity = match side with Buy->ask_liquidity|Sell->bid_liquidity in
                    if units<minimum || units>maximum || units>liquidity then
                      Error "FX floored units violate actual size or top-price liquidity"
                    else let units = (match side with Buy->""|Sell->"-") ^ compact units in
                      let request = `Assoc ["order",`Assoc [
                        "type",`String "MARKET";"instrument",`String name;
                        "units",`String units;"timeInForce",`String "FOK";
                        "priceBound",`String (compact bound);
                        "positionFill",`String "OPEN_ONLY";
                        "clientExtensions",`Assoc ["id",`String client_id];
                        "tradeClientExtensions",`Assoc ["id",`String client_id];
                        "stopLossOnFill",`Assoc ["price",`String (compact stop);
                          "timeInForce",`String "GTC"]]] in
                      Ok {request;units;budget_usd=compact budget;
                        valuation_unit_usd=compact factor;quote_time;
                        conversion_poll_time;received_ns}
