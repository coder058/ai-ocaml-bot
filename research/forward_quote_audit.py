"""Frozen first-observed long quote references, NOT fills or broker P&L.

Reject unavailable/stale quotes, delayed exits and temporal split crossings.
No price is inferred from a candle. No policy can be authorized by this report.
"""
import argparse
import hashlib
import json
import math
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from decision_quote_capture import normalize, quote_time, MAX_QUOTE_AGE_SECONDS
from forward_pattern_audit import FRAME_SECONDS, BPS, read_journal


def reference(value):
    if not isinstance(value,dict) or value.get("purpose")!="observed_quote_reference_not_execution" or value.get("orderAuthority") is not False or value.get("winProbability") is not None:
        raise ValueError("quote authority or provenance invalid")
    venue,symbol=value["venue"],value["symbol"]
    if venue not in ("Alpaca crypto","Alpaca equities") or symbol=="AAPL" or venue=="Alpaca crypto" and symbol not in ("BTC/USD","ETH/USD","SOL/USD"):
        raise ValueError("quote instrument unsupported or protected")
    received_at=datetime.fromisoformat(value["receivedAt"].replace("Z","+00:00"))
    checked=normalize({"t":value["quoteAt"],"bp":value["bid"],"ap":value["ask"],"bs":value["bidSizeRaw"],"as":value["askSizeRaw"]},received_at,venue,symbol)
    if value.get("status")!="fresh" or checked["status"]!="fresh" or value.get("feed")!=checked["feed"]:
        raise ValueError("quote was not fresh on its actual source feed")
    return {**checked,"received":quote_time(value["receivedAt"]),"at":quote_time(value["quoteAt"])}


def read_quotes(path):
    rows,counts,digest=[],Counter(),hashlib.sha256()
    with path.open("rb") as source:
        size=path.stat().st_size
        while source.tell()<size:
            raw=source.readline(size-source.tell());digest.update(raw)
            if not raw.endswith(b"\n"):
                counts["partialFinalLine"]+=1;break
            counts["lines"]+=1
            try:rows.append(reference(json.loads(raw)))
            except (ValueError,KeyError,TypeError,OverflowError):counts["unusableReferences"]+=1
    return rows,{**dict(counts),"usableReferences":len(rows),"inputBytes":size,"sha256":digest.hexdigest()}


def report(frames,quotes,*,horizon_bars,max_exit_lag_seconds,split_at,crypto_taker_bps,as_of):
    if not isinstance(horizon_bars,int) or isinstance(horizon_bars,bool) or horizon_bars<=0 or not isinstance(max_exit_lag_seconds,int) or isinstance(max_exit_lag_seconds,bool) or max_exit_lag_seconds<0:
        raise ValueError("explicit positive horizon and nonnegative exit lag required")
    if isinstance(crypto_taker_bps,bool) or not math.isfinite(crypto_taker_bps) or not 0<=crypto_taker_bps<BPS:
        raise ValueError("explicit finite fee scenario required")
    split,known_at=quote_time(split_at),quote_time(as_of)
    grouped=defaultdict(list)
    for q in quotes:
        if q["received"]<=known_at:grouped[q["venue"],q["symbol"]].append(q)
    # SOURCE: first later *received* snapshot, not the best future price.
    for rows in grouped.values():rows.sort(key=lambda q:q["received"])
    rejected,labels=Counter(),[]
    for row in frames:
        if row["status"] not in ("ready","candidate"):
            rejected["signalNotReady"]+=1;continue
        if not any(value is not None for value in row["patterns"].values()):
            rejected["noFirstObservedPatternValues"]+=1;continue
        try:
            observed=quote_time(row["observedAtText"])
            entry=reference(row.get("quoteReference"))
            if (entry["venue"],entry["symbol"])!=(row["venue"],row["symbol"]) or entry["received"]>observed or observed>known_at or observed-entry["at"]>MAX_QUOTE_AGE_SECONDS:
                raise ValueError("entry scope/receipt does not precede observed features")
        except (ValueError,KeyError,TypeError,OverflowError):
            rejected["noFirstObservedFreshEntryQuote"]+=1;continue
        due=observed+FRAME_SECONDS[row["frame"]]*horizon_bars
        candidates=grouped[row["venue"],row["symbol"]]
        index=bisect_left([q["received"] for q in candidates],due)
        exit_quote=next((q for q in candidates[index:] if q["at"]>=due),None)
        if not exit_quote or exit_quote["received"]>due+max_exit_lag_seconds:
            rejected["noTimelyFreshExitReference"]+=1;continue
        if observed<split<=exit_quote["received"]:
            rejected["crossesChronologicalSplit"]+=1;continue
        ratio=exit_quote["bid"]/entry["ask"]
        # SOURCE: Alpaca charges crypto fees in the received asset; entry fee
        # reduces owned asset, exit fee reduces cash. Fee is an explicit scenario,
        # not an inferred actual account tier or allocated broker activity.
        fee=crypto_taker_bps/BPS
        modeled_net=(ratio*(1-fee)*(1-fee)-1)*BPS if row["venue"]=="Alpaca crypto" else None
        labels.append({"venue":row["venue"],"symbol":row["symbol"],"frame":row["frame"],
            "fold":"discovery" if observed<split else "validation", "patterns":row["patterns"],
            "signalObservedAt":row["observedAtText"],"entryReferenceReceivedAt":entry["receivedAt"],
            "exitReferenceReceivedAt":exit_quote["receivedAt"],"holdingSeconds":float(exit_quote["received"]-observed),
            "exitLagSeconds":float(exit_quote["received"]-due),"entryAskReference":entry["ask"],"exitBidReference":exit_quote["bid"],
            "longQuoteReferenceMoveBps":(ratio-1)*BPS,"modeledCryptoAfterFeeBps":modeled_net})
    controls=defaultdict(list);patterns=defaultdict(list)
    for row in labels:
        key=(row["venue"],row["symbol"],row["frame"],row["fold"])
        controls[key].append(row)
        for name,value in row["patterns"].items():
            if value:patterns[(*key,name,"positive_code" if value>0 else "negative_code")].append(row)
    def distribution(values, mean_name):
        return {"count":len(values),mean_name:sum(values)/len(values) if values else None,
                "positiveReferenceFraction":sum(value>0 for value in values)/len(values) if values else None}
    def stats(rows):
        nets=[row["modeledCryptoAfterFeeBps"] for row in rows if row["modeledCryptoAfterFeeBps"] is not None]
        return {"longQuoteReferences":distribution([row["longQuoteReferenceMoveBps"] for row in rows],"meanQuoteReferenceMoveBps"),
                "cryptoFeeScenario":distribution(nets,"meanModeledAfterFeeBps") if nets else None}
    comparisons=[{"venue":key[0],"symbol":key[1],"frame":key[2],"fold":key[3],"pattern":key[4],"signedCode":key[5],
                  "references":stats(rows),"sameMarketFrameFoldBaseline":stats(controls[key[:4]])} for key,rows in sorted(patterns.items())]
    return {"schema":"first_observed_long_quote_reference_v1","orderAuthority":False,"winProbability":None,"brokerPnl":None,
        "horizonBars":horizon_bars,"maxExitLagSeconds":max_exit_lag_seconds,"splitAt":split_at,"cryptoTakerBpsScenario":crypto_taker_bps,
        "labelCount":len(labels),"foldCounts":dict(Counter(row["fold"] for row in labels)),"rejected":dict(rejected),
        "comparisonCount":len(comparisons),"comparisons":comparisons,"summary":stats(labels),"labels":labels,
        "limits":["Sampled bid/ask references are not orders, fills or guaranteed executable prices",
                  "No order latency, queue, partial fills, impact or normalized size/depth model",
                  "IEX is a single exchange; equity net costs remain unknown",
                  "Crypto fee scenario is explicit, not the verified account tier or actual posted fees",
                  "Long-only reference for every signed code; no short execution assumption or pattern-derived probability",
                  "Positive reference fraction is an empirical sample statistic, not a calibrated win probability",
                  "Related frames/horizons and many pattern comparisons are dependent; no significance or policy promotion",
                  "Capture started after earlier feature records; missing first quotes cannot be retroactively repaired",
                  "Paper/reference results do not establish live profitability"]}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("journal","quotes","output"):parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--horizon-bars",type=int,required=True)
    parser.add_argument("--max-exit-lag-seconds",type=int,required=True)
    parser.add_argument("--split-at",required=True)
    parser.add_argument("--crypto-taker-bps",type=float,required=True)
    args=parser.parse_args()
    frames,frame_input=read_journal(args.journal);quotes,quote_input=read_quotes(args.quotes)
    as_of=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    result=report(frames,quotes,horizon_bars=args.horizon_bars,max_exit_lag_seconds=args.max_exit_lag_seconds,
                  split_at=args.split_at,crypto_taker_bps=args.crypto_taker_bps,as_of=as_of)
    result.update({"generatedAt":as_of,"frameInput":frame_input,"quoteInput":quote_input})
    args.output.write_text(json.dumps(result,allow_nan=False,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ["labelCount","foldCounts","rejected","comparisonCount","summary","frameInput","quoteInput"]}))
