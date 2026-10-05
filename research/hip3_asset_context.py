"""Whitelisted current public derivative metrics, no wallets or order authority.

Source: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals
The response has no observation timestamp. Actual HTTP reception is knowledge
time, not a historical bar timestamp or proof of volume/OI trend confirmation.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

INFO = "https://api.hyperliquid.xyz/info"  # SOURCE: official public info origin.
DEX = "xyz"  # SOURCE: current monitored HIP-3 catalog; no universe expansion.
# SOURCE: whitelisted documented metaAndAssetCtxs fields. Preserve native
# decimals/units; no guessed USD conversion, annualized rate or funding cost.
FIELDS = {"openInterest":"openInterestRaw", "funding":"fundingRateRaw",
          "dayNtlVlm":"dayNotionalVolumeRaw", "dayBaseVlm":"dayBaseVolumeRaw",
          "markPx":"markPriceRaw", "oraclePx":"oraclePriceRaw"}


def metadata(value):
    if not isinstance(value, dict) or not isinstance(value.get("universe"),list):
        raise ValueError("HIP-3 metadata missing")
    names=[]
    for row in value["universe"]:
        if not isinstance(row,dict) or not isinstance(row.get("name"),str) or not row["name"].startswith(DEX+":"):
            raise ValueError("wrong HIP-3 metadata namespace")
        names.append(row["name"])
    if len(set(names)) != len(names):
        raise ValueError("duplicate HIP-3 instrument")
    return value


def parse(payload, received_at):
    if received_at.tzinfo is None:
        raise ValueError("derivative context receipt has no timezone")
    if not isinstance(payload,list) or len(payload)!=2:
        raise ValueError("HIP-3 metadata/context tuple missing")
    meta=metadata(payload[0]); rows=payload[1]
    if not isinstance(rows,list) or len(rows)!=len(meta["universe"]):
        raise ValueError("HIP-3 context index scope mismatch")
    contexts={}
    for asset,row in zip(meta["universe"],rows):
        if asset.get("isDelisted"):
            continue
        entry={"symbol":asset["name"],"source":"Hyperliquid public metaAndAssetCtxs",
            "receivedAt":received_at.astimezone(timezone.utc).isoformat().replace("+00:00","Z"),
            "providerTimestamp":None,"historicalSeries":False,"orderAuthority":False,
            "winProbability":None,"units":"Provider native quantities/rate, not normalized USD or annualized funding",
            "missing":[],"confirmation":"Current received observation only; no historical price/OI trend confirmation"}
        for field,output in FIELDS.items():
            try:
                value=row.get(field) if isinstance(row,dict) else None
                if not isinstance(value,str):
                    raise ValueError("provider decimal string missing")
                decimal=Decimal(value)
                if not decimal.is_finite() or field!="funding" and decimal<0 or field in ("markPx","oraclePx") and decimal<=0:
                    raise ValueError("invalid native decimal")
                entry[output]=value
            except (ValueError,InvalidOperation):
                entry[output]=None
                entry["missing"].append(field)
        entry["status"]="descriptive" if not entry["missing"] else "partial"
        contexts[asset["name"]]=entry
    return meta,contexts


def collect(request, now=lambda:datetime.now(timezone.utc)):
    try:
        payload=request(INFO,body={"type":"metaAndAssetCtxs","dex":DEX})
        meta,contexts=parse(payload,now())
        return meta,contexts,[]
    except Exception as error:
        # Preserve the existing catalog/intraday path when new metrics fail.
        # No last-good metrics are falsely presented as newly received.
        meta=metadata(request(INFO,body={"type":"meta","dex":DEX}))
        return meta,{},[{"stage":"hip3_asset_context","error":type(error).__name__}]
