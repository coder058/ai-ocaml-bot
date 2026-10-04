(* Frozen stock/ETF paper candidate policy. Pure, no broker authority.
   Reuses the shared OCaml confluence readings; not a profitability claim. *)
type signal = { symbol:string; frame:string; bar:string; stop:float; reading:Yojson.Safe.t }
let field=Paper_broker.member
let text name row=Paper_broker.string (field name row)
let number name row=Paper_broker.float (field name row)
let client_id parts="aibotstk" ^ Digest.to_hex (Digest.string (String.concat "|" parts))
(* SOURCE: deterministic identity only; MD5 is not authentication. *)
let timestamp stamp =
  (* SOURCE: the existing Alpaca UTC quote timestamp parser's format. Pipeline
     retrievedAt includes fractional seconds; bar starts remain minute-aligned. *)
  try
    let prefix=String.sub stamp 0 16 ^ ":00Z" in
    let suffix=String.sub stamp 17 (String.length stamp-18) in
    if stamp.[String.length stamp-1]<>'Z' ||
       not (String.for_all (function '0'..'9'|'.'->true|_->false) suffix) then None
    else match Technical.parse_utc_minute prefix with
      | Some minute -> let seconds=float_of_string suffix in
        if Float.is_finite seconds && seconds>=0. && seconds<60. then Some (float_of_int minute*.60.+.seconds) else None
      | None->None
  with _->None
let fresh ~now stamp=match timestamp stamp with
  | Some at -> now>=at && now-.at<=Multi_paper.max_snapshot_age_seconds
  | None -> false
(* SOURCE: preserve the existing operational snapshot age guard, which is
   explicitly an UNCALIBRATED GUESS in Multi_paper, not fitted market evidence. *)
let signals ~now document =
  match text "policy" document,text "asOf" document,text "retrievedAt" document,
        field "orderAuthority" document,field "markets" document with
  | Some "trend_candle_confluence_v1",Some as_of,Some retrieved,Some (`Bool false),Some (`List markets)
      when fresh ~now as_of && fresh ~now retrieved ->
    let as_of_minute=int_of_float (Option.get (timestamp as_of) /. 60.) in
    let read market=match text "venue" market,text "symbol" market,field "frames" market with
      | Some "Alpaca equities",Some symbol,Some frames when Result.is_ok (Paper_stock_broker.symbol symbol) ->
        List.filter_map (fun (frame,minutes)->match field frame frames with
          | Some reading -> (match text "status" reading,text "candidate" reading,text "lastBarStart" reading,
              number "invalidationLevel" reading,number "close" reading,
              field "orderAuthority" reading,field "winProbability" reading with
            | Some "candidate",Some "long",Some bar,Some stop,Some close,Some (`Bool false),Some `Null
                when Float.is_finite stop && Float.is_finite close && stop>0. && stop<close &&
                  text "trend" reading=Some "rising" &&
                  (match field "candleShapes" reading with Some (`List shapes)->
                    List.exists (function `String "bullish_engulfing"|`String "hammer_shape"->true|_->false) shapes|_->false) ->
              (match Technical.parse_utc_minute bar with
               | Some start when start mod minutes=0 && start+minutes<=as_of_minute &&
                   start=int_of_float (now/.60.)/minutes*minutes-minutes ->
                 Some {symbol;frame;bar;stop;reading}
               | _->None)
            | _->None)
          | None->None) Frame_analysis.frames
      | _->[] in
    Ok (List.concat_map read markets)
  | _ -> Error "stock analysis source is stale, future-dated or outside the frozen read-only policy"
let entry_id signal=client_id [signal.symbol;signal.frame;signal.bar;"entry";"trend_candle_confluence_v1"]
let quote ~now ~symbol document=Result.bind (Paper_crypto_broker.parse_quote symbol document) (fun quote ->
  if Multi_paper.quote_fresh ~now quote then Ok quote
  else Error "stock executable quote is stale or future-dated")
(* SOURCE: IEX timestamped bid/ask uses the same shape as the Alpaca crypto
   quote parser. This is not a consolidated NBBO or a guaranteed execution. *)
let exit_reason ~now ~stop ~frame ~symbol quote document =
  if quote.Paper_crypto_broker.bid<=stop then Some "Latest IEX bid reached the entry candle low (local regular-session exit)"
  else match text "asOf" document,text "retrievedAt" document,field "markets" document with
    | Some as_of,Some retrieved,Some (`List markets) when fresh ~now as_of && fresh ~now retrieved ->
      let market=List.find_opt (fun row->text "venue" row=Some "Alpaca equities" && text "symbol" row=Some symbol) markets in
      let reading=Option.bind (Option.bind market (field "frames")) (field frame) in
      (match reading with Some reading when List.mem (text "status" reading) [Some "ready";Some "candidate"] &&
          text "trend" reading=Some "falling" ->
        (* GUESS: # UNCALIBRATED GUESS — same exploratory origin-frame EMA
           reversal exit as the crypto experiment; no fitted target/holding time. *)
        Some "EMA20/EMA50 trend turned falling on the owned position's origin frame"
       | _->None)
    | _->None
