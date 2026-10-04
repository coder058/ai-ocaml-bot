"""Publish a signed, read-only paper snapshot from Dublin to Vercel.

Runs on the VPS as root. It never sends Alpaca credentials to Vercel and has no
order submission method. The destination accepts only Ed25519-signed snapshots.
"""

from __future__ import annotations

import base64
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from cryptography.hazmat.primitives import serialization

PAPER_ORIGIN = "https://paper-api.alpaca.markets"  # SOURCE: Alpaca paper API origin.
ENV_PATH = Path("/etc/jsbot-paper.env")
KEY_PATH = Path("/etc/ai-ocaml-telemetry-ed25519.pem")
STATE_DIR = Path("/home/ubuntu/jsbot-paper-state")
SYNC_PATH = STATE_DIR / "telemetry-sync.json"
FEE_CACHE_PATH = STATE_DIR / "crypto-fee-cache.json"
EVENTS_PATH = STATE_DIR / "events.jsonl"
BACKFILL_PATH = STATE_DIR / "events-bootstrap.jsonl"
CAPTURE_DIR = STATE_DIR / "market-capture" / "us"
SHADOW_PATH = STATE_DIR / "multi-timeframe-shadow.json"

# SOURCE: Alpaca documents at most 500 results per Get All Orders request.
ORDER_PAGE_SIZE = 500
# GUESS: # UNCALIBRATED GUESS — stop after 20 pages to bound API work; the
# completeness field makes a truncated account history visible to viewers.
MAX_ORDER_PAGES = 20
# SOURCE: Alpaca Account Activities documents 100 results per page without date.
FILL_PAGE_SIZE = 100
# GUESS: # UNCALIBRATED GUESS — stop after 20 activity pages and disclose if
# incomplete; inspect account size before choosing a long-term archive policy.
MAX_FILL_PAGES = 20
# GUESS: # UNCALIBRATED GUESS — retain 4,000 recent journal lines in each
# snapshot; older lines remain on the VPS and must be archived separately.
MAX_JOURNAL_LINES = 4_000
# GUESS: # UNCALIBRATED GUESS — a five-minute idle heartbeat makes the
# dashboard visibly current and bounds fee-history refreshes. Measure actual
# storage, transfer, and API usage before tightening either cadence.
HEARTBEAT_SECONDS = 5 * 60


def crypto_symbol(value: object) -> str | None:
    """Canonical USD crypto identifier; no equity or arbitrary URL paths."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9]+/?USD", value):
        return None
    compact = value.replace("/", "")
    return compact[:-len("USD")] + "/USD" if len(compact) > len("USD") else None


def lab_order(client_id: object, symbol: object) -> bool:
    canonical = crypto_symbol(symbol)
    if isinstance(client_id,str) and client_id.startswith("aibotstk") and stock_symbol(symbol):
        return True
    return isinstance(client_id, str) and canonical is not None and (
        client_id.startswith("jsbotmtf") or
        client_id.startswith("jsbotbtc") and canonical == "BTC/USD")


def stock_symbol(value: object) -> str | None:
    if isinstance(value,str) and value!="AAPL" and re.fullmatch(r"[A-Z0-9][A-Z0-9.-]*",value) and not crypto_symbol(value):
        return value
    return None


def public_symbol(value: object) -> str | None:
    return crypto_symbol(value) or stock_symbol(value)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name] = value
    return values


def paper_get(path: str, credentials: dict[str, str]) -> object:
    request = urllib.request.Request(PAPER_ORIGIN + path, headers={
        "APCA-API-KEY-ID": credentials["APCA_API_KEY_ID"],
        "APCA-API-SECRET-KEY": credentials["APCA_API_SECRET_KEY"],
        "Accept": "application/json",
    })
    # GUESS: # UNCALIBRATED GUESS — fifteen-second network timeout; measure
    # observed Alpaca response times before adjusting the timer.
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def broker_orders(credentials: dict[str, str]) -> tuple[list[dict[str, object]], bool, bool]:
    orders: list[dict[str, object]] = []
    before: str | None = None
    complete = False
    for _ in range(MAX_ORDER_PAGES):
        query = {"status": "all", "limit": str(ORDER_PAGE_SIZE), "direction": "desc"}
        if before:
            query["before_order_id"] = before
        page = paper_get("/v2/orders?" + urllib.parse.urlencode(query), credentials)
        if not isinstance(page, list):
            raise ValueError("Alpaca order response was not an array")
        orders.extend(page)
        if len(page) < ORDER_PAGE_SIZE:
            complete = True
            break
        last = page[-1]
        if not isinstance(last, dict) or not isinstance(last.get("id"), str):
            raise ValueError("Alpaca order pagination has no last ID")
        before = last["id"]
    projected = []
    seen_order_ids: set[str] = set()
    unique_orders = []
    for order in orders:
        order_id = order.get("id", "")
        if not isinstance(order_id, str) or not order_id or order_id in seen_order_ids:
            continue
        seen_order_ids.add(order_id)
        unique_orders.append(order)
    owned_symbols = {"BTC/USD"} | {public_symbol(order.get("symbol"))
        for order in unique_orders if lab_order(order.get("client_order_id"), order.get("symbol"))}
    for order in unique_orders:
        order_id = order["id"]
        client_order_id = order.get("client_order_id", "")
        symbol = order.get("symbol", "")
        # SOURCE: publish this lab's crypto scope and external activity in the
        # same scope so attribution can fail closed. Protected AAPL stays private.
        if public_symbol(symbol) not in owned_symbols:
            continue
        projected.append({
            "id": order_id,
            "clientOrderId": client_order_id,
            "symbol": symbol,
            "side": order.get("side", ""),
            "status": order.get("status", ""),
            "filledQty": order.get("filled_qty", "0"),
            "submittedAt": order.get("submitted_at"),
            "assetClass": order.get("asset_class"),
            "orderType": order.get("type"),
            "timeInForce": order.get("time_in_force"),
        })
    # USD-denominated crypto fee rows do not carry an order ID or symbol. They
    # can only be attributed to the lab when every account crypto order is
    # present in the complete history and belongs to the lab.
    crypto_orders_attributable = complete and all(
        lab_order(order.get("client_order_id"), order.get("symbol"))
        for order in unique_orders
        if order.get("asset_class") == "crypto" or crypto_symbol(order.get("symbol")) is not None
    )
    return projected, complete, crypto_orders_attributable


def broker_fills(credentials: dict[str, str], orders: list[dict[str, object]]) -> tuple[list[dict[str, object]], bool]:
    by_order_id = {order["id"]: order["clientOrderId"] for order in orders}
    fills: list[dict[str, object]] = []
    token: str | None = None
    complete = False
    for _ in range(MAX_FILL_PAGES):
        query = {"direction": "desc", "page_size": str(FILL_PAGE_SIZE)}
        if token:
            query["page_token"] = token
        page = paper_get("/v2/account/activities/FILL?" + urllib.parse.urlencode(query), credentials)
        if not isinstance(page, list):
            raise ValueError("Alpaca FILL activities response was not an array")
        fills.extend(page)
        if len(page) < FILL_PAGE_SIZE:
            complete = True
            break
        last = page[-1]
        if not isinstance(last, dict) or not isinstance(last.get("id"), str):
            raise ValueError("Alpaca FILL pagination has no last ID")
        if token == last["id"]:
            raise ValueError("Alpaca FILL pagination did not advance")
        token = last["id"]
    projected = [{
        "id": fill.get("id", ""),
        "orderId": fill.get("order_id", ""),
        "symbol": fill.get("symbol", ""),
        "side": fill.get("side", ""),
        "qty": fill.get("qty", "0"),
        "price": fill.get("price", "0"),
        "transactionTime": fill.get("transaction_time"),
    } for fill in fills if fill.get("order_id") in by_order_id]
    unique_fills: dict[str, dict[str, object]] = {}
    for fill in projected:
        activity_id = str(fill.get("id", ""))
        if activity_id and activity_id not in unique_fills:
            unique_fills[activity_id] = fill
    return list(unique_fills.values()), complete


def broker_crypto_fees(credentials: dict[str, str],
                       crypto_orders_attributable: bool, *,
                       use_cache: bool = False,
                       cache_path: Path = FEE_CACHE_PATH,
                       owned_symbols: set[str] | None = None) -> dict[str, object]:
    """Summarize posted crypto fees; do not invent per-order fee attribution."""
    activities_by_id: dict[str, dict[str, object]] = {}
    fetched_at: str | None = None
    cached = None
    if use_cache and cache_path.exists():
        try:
            candidate = json.loads(cache_path.read_text(encoding="utf-8"))
            fetched_at = candidate.get("fetchedAt")
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))).total_seconds()
            # SOURCE: a future-dated cache indicates clock skew; do not trust it.
            if (0 <= age < HEARTBEAT_SECONDS and candidate.get("pagesComplete") is True and
                    isinstance(candidate.get("activities"), list)):
                cached = candidate
        except (OSError, ValueError, AttributeError, TypeError):
            cached = None

    pages_complete = True
    if cached is not None:
        activities_by_id = {row["id"]: row for row in cached["activities"]
                            if isinstance(row, dict) and isinstance(row.get("id"), str)}
    else:
        for activity_type in ("CFEE", "FEE"):
            token: str | None = None
            activity_complete = False
            for _ in range(MAX_FILL_PAGES):
                query = {"direction": "desc", "page_size": str(FILL_PAGE_SIZE)}
                if token:
                    query["page_token"] = token
                try:
                    page = paper_get(
                        f"/v2/account/activities/{activity_type}?" +
                        urllib.parse.urlencode(query), credentials,
                    )
                except (OSError, ValueError):
                    break
                if not isinstance(page, list):
                    break
                malformed_page = False
                for row in page:
                    if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                        malformed_page = True
                        break
                    if activity_type == "CFEE" or "Coin Pair Transaction Fee" in str(row.get("description", "")):
                        activities_by_id.setdefault(row["id"], row)
                if malformed_page:
                    break
                if len(page) < FILL_PAGE_SIZE:
                    activity_complete = True
                    break
                last = page[-1]
                if not isinstance(last, dict) or not isinstance(last.get("id"), str) or token == last["id"]:
                    break
                token = last["id"]
            pages_complete = pages_complete and activity_complete
        if pages_complete:
            fetched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            if use_cache:
                try:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = cache_path.with_suffix(".tmp")
                    cache_rows = [{key: row.get(key) for key in (
                        "id", "activity_type", "description", "symbol", "qty", "price",
                        "net_amount", "created_at")}
                        for row in activities_by_id.values()]
                    temporary.write_text(json.dumps({"fetchedAt": fetched_at,
                                                     "pagesComplete": True,
                                                     "activities": cache_rows}), encoding="utf-8")
                    os.chmod(temporary, 0o600)  # SOURCE: fee-cache rows are private account activity.
                    os.replace(temporary, cache_path)
                except OSError:
                    pass

    # SOURCE: decimal zero is the additive identity for broker fee activity sums.
    usd_net_amount = Decimal("0")
    btc_fee_qty = Decimal("0")
    btc_fee_value_usd = Decimal("0")
    asset_fees: dict[str, dict] = {}
    owned_symbols = owned_symbols if owned_symbols is not None else {"BTC/USD"}
    usd_rows = 0
    btc_rows = 0
    unclassified_rows = 0
    relevant_rows = 0
    last_activity_at: str | None = None
    for row in activities_by_id.values():
        description = str(row.get("description", ""))
        if ("Coin Pair Transaction Fee" not in description and
                row.get("activity_type") != "CFEE"):
            continue
        if "Coin Pair Transaction Fee" not in description:
            unclassified_rows += 1
            continue
        relevant_rows += 1
        created_at = row.get("created_at")
        if isinstance(created_at, str) and (last_activity_at is None or created_at > last_activity_at):
            last_activity_at = created_at
        try:
            if "(USD)" in description:
                usd_net_amount += Decimal(str(row.get("net_amount", "0")))
                usd_rows += 1
            elif ("(Non USD)" in description and
                  crypto_symbol(row.get("symbol")) in owned_symbols):
                qty = Decimal(str(row.get("qty", "0")))
                price = Decimal(str(row.get("price", "0")))
                symbol = crypto_symbol(row.get("symbol"))
                bucket = asset_fees.setdefault(symbol, {"qty": Decimal("0"),
                    "valueAtActivityPriceUsd": Decimal("0"), "rows": 0})
                bucket["qty"] += qty
                bucket["valueAtActivityPriceUsd"] += qty * price
                bucket["rows"] += 1
                if symbol == "BTC/USD":
                    btc_fee_qty += qty
                    btc_fee_value_usd += qty * price
                    btc_rows += 1
            else:
                unclassified_rows += 1
        except (InvalidOperation, ValueError):
            unclassified_rows += 1

    return {
        "pagesComplete": pages_complete,
        "attributedToBot": pages_complete and crypto_orders_attributable and unclassified_rows == 0,
        "activityRows": relevant_rows,
        "usdFeeRows": usd_rows,
        "btcFeeRows": btc_rows,
        "unclassifiedRows": unclassified_rows,
        "usdNetAmount": str(usd_net_amount),
        "btcFeeQty": str(btc_fee_qty),
        "btcFeeValueAtActivityPriceUsd": str(btc_fee_value_usd),
        "assetFees": {symbol: {"qty": str(values["qty"]),
            "valueAtActivityPriceUsd": str(values["valueAtActivityPriceUsd"]),
            "rows": values["rows"]} for symbol, values in asset_fees.items()},
        "lastActivityAt": last_activity_at,
        "fetchedAt": fetched_at,
    }


def journal() -> tuple[list[dict[str, str]], bool, list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    for path in (BACKFILL_PATH, EVENTS_PATH):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
                if isinstance(item.get("at"), str) and isinstance(item.get("message"), str):
                    rows.append({"at": item["at"], "message": item["message"]})
            except (json.JSONDecodeError, AttributeError):
                continue
    rows.sort(key=lambda item: item["at"])
    complete = len(rows) <= MAX_JOURNAL_LINES
    # SOURCE: the complete local journal is needed to preserve the decision
    # trace for older broker orders after the public journal window rolls on.
    decision_rows = [row for row in rows if row["message"].startswith(
        ("HOT_DECISION ", "HOT_SAMPLE "))]
    return rows[-MAX_JOURNAL_LINES:], complete, decision_rows


def public_journal(events: list[dict[str, str]],
                   orders: list[dict[str, object]]) -> list[dict[str, str]]:
    """Keep only broker lifecycle rows that explain a retained bot order."""
    bot_client_ids = {
        str(order.get("clientOrderId", "")) for order in orders
        if str(order.get("clientOrderId", "")).startswith("jsbotbtc")
    }
    lifecycle_prefixes = ("SEND ", "ACK ", "reconcile ", "REJECTED ",
                          "UNCERTAIN ", "HALT ")
    selected = []
    for event in events:
        message = event["message"]
        if not message.startswith(lifecycle_prefixes):
            continue
        order_id = next((token[3:] for token in message.split()
                         if token.startswith("id=")), "")
        if order_id in bot_client_ids:
            selected.append(event)
    return selected


def decision_history(events: list[dict[str, str]],
                     orders: list[dict[str, object]]) -> dict[str, dict[str, str]]:
    """Join logged quote decisions to broker order IDs without guessing proximity."""
    decisions: dict[str, dict[str, str]] = {}
    samples: dict[str, dict[str, str]] = {}
    for row in events:
        message = row["message"]
        if not message.startswith(("HOT_DECISION ", "HOT_SAMPLE ")):
            continue
        fields = dict(token.split("=", 1) for token in message.split()[1:]
                      if "=" in token)
        quote_time = fields.get("quote_time", "")
        if not quote_time:
            continue
        suffix = "".join(character for character in quote_time if character.isalnum())
        if message.startswith("HOT_DECISION "):
            decisions[suffix] = {key: fields[key] for key in (
                "quote_time", "policy", "receive_to_decision_ms", "trend", "reference_bid",
                "reference_ask", "current_bid", "current_ask", "cross_direction",
                "trigger_move_bps") if key in fields}
            # SOURCE: retain the actual journal timestamp, not the market's
            # quote timestamp, to verify that the trace preceded submission.
            if row.get("at"):
                decisions[suffix]["observedAt"] = row["at"]
        else:
            samples[suffix] = {key: fields[key] for key in (
                "reference_quote_time", "window_ms", "candidate") if key in fields}
    result: dict[str, dict[str, str]] = {}
    for order in orders:
        client_id = order.get("clientOrderId")
        order_id = order.get("id")
        side = order.get("side")
        if not isinstance(client_id, str) or not isinstance(order_id, str) or \
                side not in ("buy", "sell"):
            continue
        prefix = f"jsbotbtc{side}"
        if not client_id.startswith(prefix):
            continue
        suffix = client_id[len(prefix):]
        if suffix in decisions:
            result[order_id] = {**decisions[suffix], **samples.get(suffix, {})}
    return result


def service_state(credentials: dict[str, str]) -> dict[str, object]:
    active = subprocess.run(
        ["systemctl", "is-active", "--quiet", "jsbot-paper.service"], check=False,
    ).returncode == 0
    mode = "PAPER_ORDER" if active and credentials.get("PAPER_ORDERS") == "1" else (
        "MONITOR" if active else "STOPPED"
    )
    # SOURCE: installations can retain their existing private systemd unit name.
    # Configuration selects that unit without publishing its name in telemetry.
    capture_unit = credentials.get("AI_OCAML_CAPTURE_SERVICE", "ai-ocaml-market-capture.service")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*\.service", capture_unit):
        raise ValueError("Invalid capture service configuration")
    capture_active = subprocess.run(
        ["systemctl", "is-active", "--quiet", capture_unit],
        check=False,
    ).returncode == 0
    return {"active": active, "mode": mode, "captureActive": capture_active}


def public_positions(positions: list[dict[str, object]],
                     owned_symbols: set[str] | None = None) -> list[dict[str, object]]:
    """Publish only symbols with actual lab orders; exclude private AAPL."""
    owned_symbols = owned_symbols if owned_symbols is not None else {"BTC/USD"}
    return [{
        "symbol": str(position.get("symbol", "")),
        "qty": str(position.get("qty", "")),
        "side": str(position.get("side", "")),
        "avgEntryPrice": str(position.get("avg_entry_price", "")),
        "marketValue": position.get("market_value"),
        "currentPrice": position.get("current_price"),
        "unrealizedPl": position.get("unrealized_pl"),
        "protected": False,
        "assetClass": position.get("asset_class"),
    } for position in positions if public_symbol(position.get("symbol")) in owned_symbols]


def connection_state() -> dict:
    """Whitelist public connection fields; private broker ledgers never cross SSH."""
    files={"orderStream":("paper-order-capture.json",("asOf","provider","connected","reason",
        "lastOrderEventAt","eventCount","orderAuthority","restReconciliationRequired","errorClass")),
        "stocks":("stock-connection.json",("asOf","provider","product","connected","sessionOpen",
        "nextOpen","automaticStrategy","executionGateArmed","canSubmitNow","feed","accountReady")),
        "stockAuto":("stock-auto.json",("asOf","mode","automaticStrategy","newEntriesEnabled","sessionOpen",
        "entryUsd","maxOpenPositions","eligibleLongSignals","routerInvocations","abstentions","ownedPositions","winProbability","stopHandling")),
        "stockStream":("stock-capture.json",("asOf","provider","product","feed","connected","symbols",
        "symbolLimit","quoteCount","barCount","orderAuthority","fullNbbo","lastMarketEventAt","reason","errorClass")),
        "fx":("fx-connection.json",("asOf","provider","product","connected","executionMode","automaticStrategy",
        "orderAuthority","executionAdapterAvailable","reason","framesRequested","instruments","monitoredPairs","catalogCount")),
        "catalog":("instrument-catalog.json",("asOf","provider","catalogOnly","stockEtfCount","monitoredStocks",
        "unavailableRequestedStocks","cryptoAllowed","protectedStocks"))}
    result={}
    for name,(filename,keys) in files.items():
        path=STATE_DIR/filename
        if not path.exists():continue
        try:
            row=json.loads(path.read_text());result[name]={key:row.get(key) for key in keys}
        except (OSError,ValueError):result[name]={"connected":False,"reason":"connection_status_unreadable"}
    return result


def stock_order_evidence(orders:list[dict],path:Path=STATE_DIR/"stock-paper-events.jsonl") -> dict:
    by_client={row["clientOrderId"]:row["id"] for row in orders if
        str(row.get("clientOrderId","")).startswith("aibotstk") and lab_order(row.get("clientOrderId"),row.get("symbol"))}
    evidence={}
    if not path.exists():return evidence
    for line in path.read_text().splitlines():
        try:row=json.loads(line)
        except ValueError:continue
        if isinstance(row,dict) and row.get("kind")=="DECISION" and row.get("clientOrderId") in by_client:
            evidence[by_client[row["clientOrderId"]]]={"policy":"explicit_stock_paper_request",
                "reason":str(row.get("reason","")),"observedAt":str(row.get("at","")),"frame":"manual"}
            detail=row.get("detail",{})
            if isinstance(detail,dict) and detail.get("policy")=="trend_candle_confluence_v1":
                reading=detail.get("reading",{})
                if not isinstance(reading,dict):reading={}
                values={"policy":detail["policy"],"frame":detail.get("frame"),"signal_bar":detail.get("signalBar"),
                    "invalidation_level":detail.get("invalidationLevel"),"ema20":reading.get("ema20"),
                    "ema50":reading.get("ema50"),"rsi14":reading.get("rsi14"),"trend":reading.get("trend"),
                    "candle_shapes":", ".join(reading.get("candleShapes",[]))}
                preflight=detail.get("preflight",{})
                if isinstance(preflight,dict):
                    values.update({"trigger_bid":preflight.get("bid"),"trigger_ask":preflight.get("ask"),
                        "trigger_quote_time":preflight.get("quoteTime"),"preflight_evidence":json.dumps({key:preflight.get(key)
                        for key in ("regularSessionOpen","accountReady","buyingPowerChecked","buyingPowerSufficient",
                                    "brokerQuantity","ownedQuantity","existingOrders")})})
                evidence[by_client[row["clientOrderId"]]].update({key:str(value) for key,value in values.items() if value is not None})
    return evidence


def multi_order_evidence(orders: list[dict],
                         path: Path = STATE_DIR / "multi-paper-events.jsonl") -> dict[str, dict[str, str]]:
    """Join an explicit client order ID, never the nearest technical reading."""
    by_client = {row["clientOrderId"]: row["id"] for row in orders
                 if lab_order(row.get("clientOrderId"), row.get("symbol"))}
    result = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # SOURCE: a torn last append cannot invent decision evidence.
        if not isinstance(row, dict):
            continue
        client_id = row.get("clientOrderId")
        if row.get("kind") != "DECISION" or client_id not in by_client:
            continue
        reading = row.get("reading", {})
        values = {"policy": row.get("policy"), "reason": row.get("reason"), "observedAt": row.get("at"),
            "frame": row.get("frame"), "signal_bar": row.get("signalBar"),
            "invalidation_level": reading.get("invalidationLevel"),
            "ema20": reading.get("ema20"), "ema50": reading.get("ema50"),
            "rsi14": reading.get("rsi14"), "macd": reading.get("macd"),
            "macd_signal": reading.get("macdSignal"), "trend": reading.get("trend"),
            "candle_shapes": ", ".join(reading.get("candleShapes", [])),
            "bar_close": reading.get("close"), "trigger_bid": reading.get("triggerBid"),
            "trigger_ask": reading.get("triggerAsk"), "trigger_quote_time": reading.get("triggerQuoteTime")}
        result[by_client[client_id]] = {key: str(value) for key, value in values.items()
                                      if value is not None}
    return result


def capture_state(service: dict[str, object]) -> dict[str, object]:
    today = datetime.now(timezone.utc).date().isoformat()
    path = CAPTURE_DIR / f"{today}.jsonl"
    if not path.exists():
        return {"active": service["captureActive"], "lastEventAt": None, "bytesToday": 0}
    stat = path.stat()
    return {
        "active": service["captureActive"],
        "lastEventAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
        "bytesToday": stat.st_size,
    }


def latest_fields(events: list[dict[str, str]], prefix: str) -> dict[str, str] | None:
    for row in reversed(events):
        message = row["message"]
        if message.startswith(prefix):
            result = {"observedAt": row["at"]}
            for token in message.split()[1:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    result[key] = value
            return result
    return None


def analysis_state(events: list[dict[str, str]]) -> dict[str, object]:
    latest_five_event = next((row for row in reversed(events) if row["message"].startswith(
        ("TECHNICAL_5M ", "TECHNICAL_5M_UNAVAILABLE "))), None)
    five = (latest_fields([latest_five_event], "TECHNICAL_5M ")
            if latest_five_event is not None else None)
    decision = latest_fields(events, "HOT_DECISION ")
    return {
        "fiveMinute": None if five is None else {
            "observedAt": five.get("observedAt"),
            "retrievedAt": five.get("retrieved_at"),
            "lastBarAt": five.get("last_bar"),
            "contiguousBars": int(five.get("contiguous_bars", "0")),
            "trend": five.get("trend", "warming"),
            "probability": None,
            "orderAuthority": False,
        },
        "lastDecision": None if decision is None else {
            "observedAt": decision.get("observedAt"),
            "quoteTime": decision.get("quote_time"),
            "policy": decision.get("policy"),
            "receiveToDecisionMs": decision.get("receive_to_decision_ms"),
            "contextFrame": decision.get("context_frame"),
            "contextBar": decision.get("context_bar"),
            "trend": decision.get("trend"),
        },
    }


def significant_digest(events: list[dict[str, str]], service: dict[str, object],
                       document: dict[str, object]) -> str:
    meaningful = [event for event in events if event["message"].startswith((
        "SEND ", "ACK ", "reconcile ", "HALT ", "DATA_ERROR ",
        "REJECTED ", "UNCERTAIN ", "start ", "TECHNICAL_5M ",
        "HOT_DECISION ",
    ))]
    orders = [{key: order.get(key) for key in ("id", "status", "filledQty")}
              for order in document["orders"]]
    fills = [fill["id"] for fill in document["fills"]]
    # SOURCE: a changed public position projection needs one immediate signed upload.
    payload = json.dumps({"projection": "paper_pnl_posted_fees_v1", "service": service, "events": meaningful,
                          "orders": orders, "fills": fills,
                          "cryptoFees": document["cryptoFees"]}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def market_research_state(path: Path = SHADOW_PATH) -> dict | None:
    """Publish a small, market-only projection of the private shadow snapshot."""
    if not path.exists():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("orderAuthority") is not False:
        raise ValueError("invalid read-only market shadow")
    if not isinstance(document.get("asOf"), str) or not isinstance(document.get("symbols"), list):
        raise ValueError("market shadow lacks timestamp or symbols")
    rows = []
    for item in document["symbols"]:
        if not isinstance(item, dict) or not isinstance(item.get("symbol"), str) or not isinstance(item.get("frames"), dict):
            raise ValueError("market shadow row is invalid")
        frames = {}
        for name in ("1m", "5m", "30m", "60m", "240m"):
            frame = item["frames"].get(name)
            if not isinstance(frame, dict):
                raise ValueError("market shadow frame is missing")
            frames[name] = {key: frame.get(key) for key in
                            ("completeBars", "contiguousTailBars", "lastBarStart", "trend", "candleShapes")}
        rows.append({"symbol": item["symbol"], "frames": frames})
    return {"asOf": document["asOf"], "symbols": rows,
            "orderAuthority": False, "winProbability": None}


def snapshot(credentials: dict[str, str], service: dict[str, object],
             events: list[dict[str, str]], journal_complete: bool,
             decision_events: list[dict[str, str]], *,
             cache_fees: bool = False) -> dict[str, object]:
    positions = paper_get("/v2/positions", credentials)
    orders, orders_complete, crypto_orders_attributable = broker_orders(credentials)
    owned_symbols = {"BTC/USD"} | {public_symbol(order.get("symbol"))
        for order in orders if lab_order(order.get("clientOrderId"), order.get("symbol"))}
    fills, fills_complete = broker_fills(credentials, orders)
    crypto_fees = broker_crypto_fees(credentials, crypto_orders_attributable,
                                     use_cache=cache_fees, owned_symbols=owned_symbols)
    if not isinstance(positions, list):
        raise ValueError("Alpaca positions response has an unexpected shape")
    document = {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "Dublin OCaml paper service",
        "service": service,
        "capture": capture_state(service),
        "analysis": analysis_state(events),
        "positions": public_positions(positions, owned_symbols),
        "orders": orders,
        "ordersComplete": orders_complete,
        "fills": fills,
        "fillsComplete": fills_complete,
        "cryptoFees": crypto_fees,
        "decisionHistory": {**decision_history(decision_events, orders), **multi_order_evidence(orders),**stock_order_evidence(orders)},
        "connections":connection_state(),
        "journal": public_journal(events, orders),
        "journalComplete": journal_complete,
    }
    for name, filename in (("marketPipeline", "market-pipeline.json"),
                           ("multiPaper", "multi-paper.json")):
        optional = STATE_DIR / filename
        if optional.exists():
            try:
                document[name] = json.loads(optional.read_text())
            except (OSError, ValueError):
                document[name + "Error"] = "Optional analysis/execution snapshot is unreadable"
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Check read-only broker snapshot without uploading")
    args = parser.parse_args()
    credentials = read_env(ENV_PATH)
    endpoint = os.environ.get("AI_OCAML_MONITOR_INGEST_URL", "")
    if not args.dry_run and not endpoint.startswith("https://"):
        print("telemetry: AI_OCAML_MONITOR_INGEST_URL must be HTTPS", file=sys.stderr)
        return 1
    events, journal_complete, decision_events = journal()
    service = service_state(credentials)
    document = snapshot(credentials, service, events, journal_complete,
                        decision_events, cache_fees=not args.dry_run)
    digest = significant_digest(events, service, document)
    previous = {}
    if SYNC_PATH.exists():
        try:
            previous = json.loads(SYNC_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    now = datetime.now(timezone.utc).timestamp()
    if not args.dry_run and digest == previous.get("digest") and now - float(previous.get("sentAt", 0)) < HEARTBEAT_SECONDS:
        print("telemetry: unchanged, heartbeat not due")
        return 0
    body = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    # GUESS: # UNCALIBRATED GUESS — match the 1 MiB ingestion limit on Vercel;
    # archive/paginate history when this becomes insufficient.
    if len(body) > 1_048_576:
        raise ValueError("telemetry exceeds the signed endpoint limit")
    if args.dry_run:
        five = document["analysis"]["fiveMinute"]
        fee_summary = document["cryptoFees"]
        bot_ids = {order["id"] for order in document["orders"]
                   if str(order.get("clientOrderId", "")).startswith("jsbotbtc")}
        buy_notional = Decimal("0")
        sell_notional = Decimal("0")
        buy_qty = Decimal("0")
        sell_qty = Decimal("0")
        for fill in document["fills"]:
            if fill.get("orderId") not in bot_ids or fill.get("symbol") not in ("BTCUSD", "BTC/USD"):
                continue
            qty = Decimal(str(fill["qty"]))
            notional = qty * Decimal(str(fill["price"]))
            if fill.get("side") == "buy":
                buy_qty += qty
                buy_notional += notional
            elif fill.get("side") == "sell":
                sell_qty += qty
                sell_notional += notional
        btc_positions = [position for position in document["positions"]
                         if position.get("symbol") in ("BTCUSD", "BTC/USD")]
        position_qty = Decimal(str(btc_positions[0]["qty"])) if btc_positions else Decimal("0")
        position_mark = Decimal(str(btc_positions[0]["marketValue"])) if btc_positions else Decimal("0")
        btc_fee_qty = Decimal(str(fee_summary["btcFeeQty"]))
        quantity_residual = position_qty - (buy_qty - sell_qty + btc_fee_qty)
        # SOURCE: Alpaca crypto fees debit the received asset; BTC fees are
        # already reflected in broker inventory and must not be deducted twice.
        provisional_after_posted_usd_fees = (
            sell_notional - buy_notional + position_mark +
            Decimal(str(fee_summary["usdNetAmount"]))
        ) if fee_summary["attributedToBot"] else None
        print(f"telemetry: dry run, snapshot_at={document['generatedAt']}, mode={service['mode']}, {len(document['positions'])} positions, {len(document['orders'])} orders, {len(document['fills'])} fills, {len(events)} events, {len(document['decisionHistory'])} order decisions, complete_orders={document['ordersComplete']}, complete_fills={document['fillsComplete']}, complete_fee_pages={fee_summary['pagesComplete']}, fee_fetched_at={fee_summary['fetchedAt']}, fee_activity_rows={fee_summary['activityRows']}, fee_usd_net={fee_summary['usdNetAmount']}, btc_fee_qty={fee_summary['btcFeeQty']}, fee_attributed_to_bot={fee_summary['attributedToBot']}, bot_fill_cash_delta={sell_notional - buy_notional}, broker_btc_mark={position_mark}, provisional_after_posted_usd_fees={provisional_after_posted_usd_fees}, btc_qty_residual={quantity_residual}, complete_journal={journal_complete}, five_minute_trend={five['trend'] if five else 'unavailable'}, five_minute_last_bar={five['lastBarAt'] if five else 'unavailable'}, {len(body)} bytes")
        return 0
    private_key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    signature = base64.b64encode(private_key.sign(body)).decode("ascii")
    request = urllib.request.Request(endpoint, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-AI-OCaml-Signature": signature,
    })
    with urllib.request.urlopen(request, timeout=15) as response:
        acknowledgement = json.load(response)
    if acknowledgement.get("accepted") is not True:
        raise ValueError("monitor endpoint did not acknowledge the signed snapshot")
    temporary = SYNC_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps({"digest": digest, "sentAt": now}), encoding="utf-8")
    os.chmod(temporary, 0o600)  # SOURCE: owner-only local synchronization state.
    os.replace(temporary, SYNC_PATH)
    print(f"telemetry: uploaded signed paper snapshot, {len(document['orders'])} broker orders, {len(document['fills'])} fills, {len(events)} journal events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
