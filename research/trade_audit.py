"""Audit every Alpaca paper trade made by this bot, from complete broker history.

Read-only: it issues GET requests to the hardcoded Alpaca paper origin and never
submits, cancels or modifies an order. Run it on the VPS (credentials from
/etc/jsbot-paper.env) or anywhere with paper keys in the environment:

    python3 research/trade_audit.py --env /etc/jsbot-paper.env \\
        --state-dir /home/ubuntu/jsbot-paper-state --output-dir audit-out

Or re-run the analysis offline on a saved snapshot (no network):

    python3 research/trade_audit.py --snapshot audit-out/raw --output-dir audit-out

Outputs: raw broker JSON (private account data; no credentials), trades.csv (one
row per order), round-trips.csv (FIFO closed lots), trade-audit.json and
TRADE-AUDIT.md. Paper fills are simulated; nothing here is live profitability.
Stdlib only, Python 3.10+.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

PAPER_ORIGIN = "https://paper-api.alpaca.markets"  # SOURCE: the only origin this bot ever traded.
ORDER_PAGE = 500  # SOURCE: Alpaca Get All Orders maximum limit.
ACTIVITY_PAGE = 100  # SOURCE: Alpaca Account Activities page size.
MAX_PAGES = 2000  # Safety bound only; reaching it marks the history incomplete.
ZERO = Decimal("0")

# Client-ID namespaces written by each executor in this repository.
STRATEGIES = (
    ("jsbotbtc", "quote_cross_30s_v1 (legacy BTC)"),
    ("jsbotmtf", "trend_candle_confluence_v1 (crypto multi-frame)"),
    ("aibotstk", "stock router (confluence or monthly_trend_v1)"),
    ("aibottrc", "crypto_monthly_trend_v1 (BTC trend)"),
)
# SOURCE: user's per-order maximum ($500) and legacy BTC exposure ceiling.
ORDER_CAP_USD = Decimal("500")
# SOURCE: published Alpaca tier-1 crypto taker fee, used only for a labelled
# estimate; posted fee rows carry no order ID and cannot be joined per order.
EST_TAKER_FEE = Decimal("0.0025")
CRYPTO_ENTRY_UNIVERSE = {"BTC/USD", "ETH/USD", "SOL/USD"}
PROTECTED = {"AAPL"}


def dec(value) -> Decimal:
    try:
        return Decimal(str(value)) if value not in (None, "") else ZERO
    except InvalidOperation:
        return ZERO


def crypto_symbol(symbol) -> str | None:
    if not isinstance(symbol, str):
        return None
    compact = symbol.replace("/", "").upper()
    if len(compact) > 3 and compact.endswith("USD") and compact.isalnum() and (
            "/" in symbol or compact[:-3] in {"BTC", "ETH", "SOL"} or len(compact) > 6):
        return compact[:-3] + "/USD"
    return None


def norm_symbol(symbol) -> str:
    return crypto_symbol(symbol) or str(symbol or "")


def strategy_of(client_id) -> str:
    for prefix, name in STRATEGIES:
        if isinstance(client_id, str) and client_id.startswith(prefix):
            return name
    return "external/manual"


# ---------------------------------------------------------------- fetching

def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def credentials_from(env_path: str | None) -> dict[str, str]:
    source = read_env(Path(env_path)) if env_path else dict(os.environ)
    key = source.get("APCA_API_KEY_ID") or source.get("ALPACA_API_KEY")
    secret = source.get("APCA_API_SECRET_KEY") or source.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("Alpaca paper credentials not found (APCA_API_KEY_ID / APCA_API_SECRET_KEY)")
    return {"key": key, "secret": secret}


def paper_get(path: str, creds: dict[str, str]):
    request = urllib.request.Request(PAPER_ORIGIN + path, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"], "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_orders(get) -> tuple[list[dict], bool]:
    """Walk backwards by submission time; dedupe; stop when a page adds nothing."""
    orders: dict[str, dict] = {}
    until = None
    for _ in range(MAX_PAGES):
        query = {"status": "all", "limit": str(ORDER_PAGE), "direction": "desc", "nested": "false"}
        if until:
            query["until"] = until
        page = get("/v2/orders?" + urllib.parse.urlencode(query))
        if not isinstance(page, list):
            raise ValueError("orders response is not a list")
        new = [o for o in page if isinstance(o, dict) and o.get("id") and o["id"] not in orders]
        for order in new:
            orders[order["id"]] = order
        if len(page) < ORDER_PAGE:
            return list(orders.values()), True
        if not new:
            # A full page with nothing new means >500 orders share one timestamp.
            return list(orders.values()), False
        until = min(str(o.get("submitted_at") or o.get("created_at")) for o in page)
    return list(orders.values()), False


def fetch_activities(get, kind: str) -> tuple[list[dict], bool]:
    rows: dict[str, dict] = {}
    token = None
    for _ in range(MAX_PAGES):
        query = {"direction": "desc", "page_size": str(ACTIVITY_PAGE)}
        if token:
            query["page_token"] = token
        page = get(f"/v2/account/activities/{kind}?" + urllib.parse.urlencode(query))
        if not isinstance(page, list):
            raise ValueError(f"{kind} response is not a list")
        for row in page:
            if isinstance(row, dict) and row.get("id"):
                rows.setdefault(row["id"], row)
        if len(page) < ACTIVITY_PAGE:
            return list(rows.values()), True
        last = page[-1].get("id") if isinstance(page[-1], dict) else None
        if not last or last == token:
            return list(rows.values()), False
        token = last
    return list(rows.values()), False


def fetch_snapshot(creds: dict[str, str], raw_dir: Path) -> dict:
    get = lambda path: paper_get(path, creds)  # noqa: E731
    orders, orders_complete = fetch_orders(get)
    fills, fills_complete = fetch_activities(get, "FILL")
    cfee, cfee_complete = fetch_activities(get, "CFEE")
    fee, fee_complete = fetch_activities(get, "FEE")
    snapshot = {
        "fetchedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "origin": PAPER_ORIGIN,
        "orders": orders, "ordersComplete": orders_complete,
        "fills": fills, "fillsComplete": fills_complete,
        "fees": cfee + fee, "feesComplete": cfee_complete and fee_complete,
        "positions": get("/v2/positions"),
        "account": {k: v for k, v in get("/v2/account").items()
                    if k in ("status", "currency", "cash", "equity", "last_equity", "crypto_status")},
    }
    raw_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(raw_dir, 0o700)
    path = raw_dir / "broker-snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    os.chmod(path, 0o600)  # private account activity; never commit it
    return snapshot


# ---------------------------------------------------------------- analysis

def load_ledgers(state_dir: Path | None) -> dict[str, dict]:
    """Map client ID -> local ledger record from every executor's durable state."""
    found: dict[str, dict] = {}
    if not state_dir:
        return found

    def read(name):
        try:
            return json.loads((state_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    for name in ("stock-paper-ledger.json", "crypto-trend-ledger.json"):
        doc = read(name)
        for row in (doc or {}).get("orders", []) if isinstance(doc, dict) else []:
            if isinstance(row, dict) and row.get("clientOrderId"):
                policy = ((row.get("analysisEvidence") or {}).get("policy") if isinstance(row.get("analysisEvidence"), dict) else None)
                found[row["clientOrderId"]] = {"ledger": name, "state": row.get("state"), "policy": policy}
    doc = read("multi-paper-ledger.json")
    for ticket in (doc or {}).get("tickets", []) if isinstance(doc, dict) else []:
        if not isinstance(ticket, dict):
            continue
        if ticket.get("entryClientOrderId"):
            found.setdefault(ticket["entryClientOrderId"], {"ledger": "multi-paper-ledger.json", "state": "resolved"})
        pending = ticket.get("pending")
        if isinstance(pending, dict) and pending.get("clientOrderId"):
            found[pending["clientOrderId"]] = {"ledger": "multi-paper-ledger.json", "state": "pending"}
    # Exits and earlier attempts are only in the append-only DECISION journals.
    for name in ("multi-paper-events.jsonl", "stock-paper-events.jsonl", "crypto-trend-events.jsonl"):
        try:
            lines = (state_dir / name).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("kind") == "DECISION" and row.get("clientOrderId"):
                found.setdefault(row["clientOrderId"], {"ledger": name, "state": "recorded"})
    return found


def classify_stock(order: dict, ledgers: dict) -> str:
    record = ledgers.get(order.get("client_order_id"), {})
    if record.get("policy") == "monthly_trend_v1":
        return "monthly_trend_v1 (ETF trend)"
    if record.get("policy") == "trend_candle_confluence_v1":
        return "trend_candle_confluence_v1 (stocks)"
    return strategy_of(order.get("client_order_id"))


def audit(snapshot: dict, ledgers: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    orders = {o["id"]: o for o in snapshot["orders"] if isinstance(o, dict) and o.get("id")}
    anomalies: list[dict] = []

    def flag(kind, detail, order=None):
        anomalies.append({"kind": kind, "detail": detail,
                          **({"orderId": order.get("id"), "clientOrderId": order.get("client_order_id"),
                              "symbol": order.get("symbol")} if order else {})})

    strategy = {}
    for oid, order in orders.items():
        name = strategy_of(order.get("client_order_id"))
        if name.startswith("stock router"):
            name = classify_stock(order, ledgers)
        strategy[oid] = name

    # Duplicate client IDs across distinct broker orders.
    by_cid = defaultdict(list)
    for order in orders.values():
        by_cid[order.get("client_order_id")].append(order)
    for cid, group in by_cid.items():
        if cid and len(group) > 1:
            flag("duplicate_client_id", f"{len(group)} broker orders share client ID {cid}", group[0])

    # Fills joined to orders.
    fills_by_order = defaultdict(list)
    orphan_fills = 0
    for fill in snapshot["fills"]:
        if fill.get("order_id") in orders:
            fills_by_order[fill["order_id"]].append(fill)
        else:
            orphan_fills += 1
    if orphan_fills:
        anomalies.append({"kind": "fills_without_order", "detail": f"{orphan_fills} FILL activities reference orders absent from order history"})

    trades = []
    for oid, order in orders.items():
        fills = fills_by_order.get(oid, [])
        fill_qty = sum((dec(f.get("qty")) for f in fills), ZERO)
        filled = dec(order.get("filled_qty"))
        price = dec(order.get("filled_avg_price"))
        bot = strategy[oid] != "external/manual"
        requested = dec(order.get("qty"))
        notional = filled * price
        if bot and fills and fill_qty != filled:
            flag("fill_sum_mismatch", f"FILL activities sum {fill_qty} but order filled_qty {filled}", order)
        if bot and requested and filled > requested:
            flag("overfill", f"filled {filled} > requested {requested}", order)
        if bot and norm_symbol(order.get("symbol")) in PROTECTED:
            flag("protected_symbol_traded", "bot namespace order on protected AAPL", order)
        if bot and order.get("side") == "buy" and notional > ORDER_CAP_USD:
            flag("over_order_cap", f"buy notional {notional:.2f} exceeds ${ORDER_CAP_USD}", order)
        status = order.get("status")
        if status not in ("filled", "canceled", "expired", "rejected", "done_for_day", "replaced"):
            submitted = order.get("submitted_at") or order.get("created_at")
            try:
                age_h = (now - datetime.fromisoformat(str(submitted).replace("Z", "+00:00"))).total_seconds() / 3600
            except ValueError:
                age_h = None
            if bot and (age_h is None or age_h > 24):
                flag("stale_open_order", f"status {status} for {age_h and round(age_h)} hours", order)
        if bot and status == "rejected":
            flag("broker_rejected", "order rejected by broker", order)
        if bot and order.get("side") == "buy" and crypto_symbol(order.get("symbol")) and \
                crypto_symbol(order.get("symbol")) not in CRYPTO_ENTRY_UNIVERSE:
            anomalies.append({"kind": "altcoin_entry", "orderId": oid, "clientOrderId": order.get("client_order_id"),
                              "symbol": order.get("symbol"), "detail": f"altcoin buy at {order.get('submitted_at')} "
                              "(entries were later restricted to BTC/ETH/SOL; informational)"})
        cid = order.get("client_order_id")
        ledger = ledgers.get(cid)
        if bot and ledgers and strategy[oid] != "quote_cross_30s_v1 (legacy BTC)" and ledger is None:
            flag("no_local_ledger_record", "broker order has no durable local ledger record", order)
        if ledger and ledger.get("state") == "pending" and status in ("filled", "canceled", "expired", "rejected"):
            flag("ledger_pending_but_broker_terminal", f"ledger pending, broker {status}", order)
        trades.append({
            "orderId": oid, "clientOrderId": cid, "strategy": strategy[oid],
            "symbol": norm_symbol(order.get("symbol")), "side": order.get("side"), "type": order.get("type"),
            "timeInForce": order.get("time_in_force"), "requestedQty": order.get("qty"),
            "requestedNotional": order.get("notional"), "limitPrice": order.get("limit_price"),
            "status": status, "filledQty": str(filled), "filledAvgPrice": str(price),
            "filledNotional": str(notional.quantize(Decimal("0.000001"))) if filled else "0",
            "fillRows": len(fills), "submittedAt": order.get("submitted_at"), "filledAt": order.get("filled_at"),
            "ledger": (ledger or {}).get("ledger"), "ledgerState": (ledger or {}).get("state"),
        })

    # Local ledger rows the broker never saw (pending ones are actionable).
    if ledgers:
        broker_cids = {o.get("client_order_id") for o in orders.values()}
        for cid, record in ledgers.items():
            if cid not in broker_cids and record.get("state") == "pending":
                anomalies.append({"kind": "ledger_pending_not_at_broker", "clientOrderId": cid,
                                  "detail": f"{record['ledger']} pending but broker has no such order"})

    # FIFO round trips per strategy and symbol, from fills in time order.
    lots: dict[tuple, list] = defaultdict(list)
    round_trips = []
    events = []
    for oid, fills in fills_by_order.items():
        if strategy[oid] == "external/manual":
            continue
        for fill in fills:
            events.append((str(fill.get("transaction_time")), fill.get("id"), oid, fill))
    events.sort(key=lambda e: (e[0], str(e[1])))
    unmatched_sells = defaultdict(lambda: ZERO)
    for when, _, oid, fill in events:
        key = (strategy[oid], norm_symbol(fill.get("symbol")))
        qty, px = dec(fill.get("qty")), dec(fill.get("price"))
        if fill.get("side") == "buy":
            lots[key].append([qty, px, when, oid])
            continue
        remaining = qty
        while remaining > 0 and lots[key]:
            lot = lots[key][0]
            take = min(remaining, lot[0])
            gross = take * (px - lot[1])
            est_fee = take * (px + lot[1]) * EST_TAKER_FEE if crypto_symbol(key[1]) else ZERO
            try:
                hold = (datetime.fromisoformat(when.replace("Z", "+00:00")) -
                        datetime.fromisoformat(lot[2].replace("Z", "+00:00"))).total_seconds()
            except ValueError:
                hold = None
            round_trips.append({"strategy": key[0], "symbol": key[1], "qty": str(take),
                                "entryPrice": str(lot[1]), "exitPrice": str(px), "entryAt": lot[2], "exitAt": when,
                                "holdSeconds": hold, "grossPnlUsd": str(gross), "estFeesUsd": str(est_fee),
                                "estNetPnlUsd": str(gross - est_fee), "entryOrderId": lot[3], "exitOrderId": oid})
            lot[0] -= take
            remaining -= take
            if lot[0] <= 0:
                lots[key].pop(0)
        if remaining > 0:
            unmatched_sells[key] += remaining
    for (name, symbol), qty in unmatched_sells.items():
        # Buy fees are charged in the received asset, so sells can only exceed
        # gross buys if inventory came from elsewhere (carry-in or history gap).
        anomalies.append({"kind": "sell_exceeds_owned_buys", "detail": f"{name} {symbol}: sold {qty} more than bought"})

    # Posted fees: summarized only, never joined per order (rows carry no order ID).
    fee_usd = ZERO
    fee_asset = defaultdict(lambda: ZERO)
    fee_asset_usd = defaultdict(lambda: ZERO)
    for row in snapshot["fees"]:
        description = str(row.get("description", ""))
        if "(USD)" in description:
            fee_usd += dec(row.get("net_amount"))
        elif crypto_symbol(row.get("symbol")):
            symbol = crypto_symbol(row.get("symbol"))
            fee_asset[symbol] += dec(row.get("qty"))
            fee_asset_usd[symbol] += dec(row.get("qty")) * dec(row.get("price"))

    # Per-strategy summary and inventory reconciliation.
    positions = {norm_symbol(p.get("symbol")): p for p in snapshot.get("positions") or [] if isinstance(p, dict)}
    summary = {}
    net_by_symbol = defaultdict(lambda: ZERO)
    for trade in trades:
        if trade["strategy"] == "external/manual":
            continue
        s = summary.setdefault(trade["strategy"], {"orders": 0, "filledOrders": 0, "partiallyFilled": 0,
            "canceledNoFill": 0, "rejected": 0, "fillRows": 0, "buyNotionalUsd": ZERO, "sellNotionalUsd": ZERO,
            "symbols": set(), "first": None, "last": None})
        s["orders"] += 1
        filled = dec(trade["filledQty"])
        if trade["status"] == "filled":
            s["filledOrders"] += 1
        elif filled > 0:
            s["partiallyFilled"] += 1
        elif trade["status"] == "rejected":
            s["rejected"] += 1
        else:
            s["canceledNoFill"] += 1
        s["fillRows"] += trade["fillRows"]
        notional = dec(trade["filledNotional"])
        s["buyNotionalUsd" if trade["side"] == "buy" else "sellNotionalUsd"] += notional
        s["symbols"].add(trade["symbol"])
        when = trade["submittedAt"]
        s["first"] = min(filter(None, [s["first"], when])) if when else s["first"]
        s["last"] = max(filter(None, [s["last"], when])) if when else s["last"]
        net_by_symbol[trade["symbol"]] += filled if trade["side"] == "buy" else -filled
    for name, s in summary.items():
        trips = [t for t in round_trips if t["strategy"] == name]
        gross = sum((dec(t["grossPnlUsd"]) for t in trips), ZERO)
        est = sum((dec(t["estFeesUsd"]) for t in trips), ZERO)
        open_qty = {k[1]: sum((lot[0] for lot in v), ZERO) for k, v in lots.items() if k[0] == name and v}
        s.update({"roundTrips": len(trips), "grossRealizedUsd": gross, "estTakerFeesUsd": est,
                  "estNetRealizedUsd": gross - est,
                  "grossWinningTrips": sum(1 for t in trips if dec(t["grossPnlUsd"]) > 0),
                  "estNetWinningTrips": sum(1 for t in trips if dec(t["estNetPnlUsd"]) > 0),
                  "openLotQty": {k: str(v) for k, v in open_qty.items() if v > 0},
                  "fillCashFlowUsd": s["sellNotionalUsd"] - s["buyNotionalUsd"],
                  "symbols": sorted(s["symbols"])})
    inventory = []
    for symbol, net in sorted(net_by_symbol.items()):
        broker = dec((positions.get(symbol) or {}).get("qty"))
        asset_fee = fee_asset.get(symbol, ZERO)  # negative quantity
        residual = broker - (net + asset_fee)
        inventory.append({"symbol": symbol, "botNetFillQty": str(net), "postedAssetFeeQty": str(asset_fee),
                          "brokerQty": str(broker), "residual": str(residual)})
        if crypto_symbol(symbol) and abs(residual) > Decimal("0.000001") * max(Decimal(1), abs(net)):
            anomalies.append({"kind": "inventory_residual", "symbol": symbol,
                              "detail": f"broker {broker} vs bot fills {net} plus posted asset fees {asset_fee}"})
    marks = sum((dec(p.get("market_value")) for sym, p in positions.items()
                 if sym in net_by_symbol and sym not in PROTECTED), ZERO)
    cash_flow = sum((s["fillCashFlowUsd"] for s in summary.values()), ZERO)
    account = {
        "fillCashFlowUsd": cash_flow, "openPositionMarksUsd": marks, "postedUsdFees": fee_usd,
        "postedAssetFeesUsdAtActivityPrice": sum(fee_asset_usd.values(), ZERO),
        "netMarkedUsd": cash_flow + marks + fee_usd,
        "note": "Same formula as the monitor: fill cash flow + bot-held marks + posted USD fees. "
                "Asset-denominated buy fees are already reflected in lower broker quantities.",
    }
    completeness = {k: snapshot.get(k) for k in ("ordersComplete", "fillsComplete", "feesComplete")}
    if not all(completeness.values()):
        anomalies.insert(0, {"kind": "incomplete_history", "detail": f"pagination incomplete: {completeness}"})
    return {"fetchedAt": snapshot.get("fetchedAt"), "completeness": completeness,
            "counts": {"brokerOrders": len(orders), "botOrders": sum(1 for t in trades if t["strategy"] != "external/manual"),
                       "fillRows": len(snapshot["fills"]), "feeRows": len(snapshot["fees"]), "roundTrips": len(round_trips)},
            "strategies": summary, "account": account, "inventory": inventory,
            "anomalies": anomalies, "trades": trades, "roundTrips": round_trips}


# ---------------------------------------------------------------- reporting

def jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(type(value))


def money(value) -> str:
    return f"{dec(value):+,.2f}"


def write_reports(result: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "trade-audit.json").write_text(json.dumps(result, indent=2, default=jsonable), encoding="utf-8")
    for name, rows in (("trades.csv", result["trades"]), ("round-trips.csv", result["roundTrips"])):
        with (out / name).open("w", newline="", encoding="utf-8") as handle:
            if rows:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
    kinds = defaultdict(int)
    for item in result["anomalies"]:
        kinds[item["kind"]] += 1
    lines = [f"# Trade audit — broker snapshot {result['fetchedAt']}", "",
             f"Completeness: {result['completeness']}", "",
             f"Broker orders {result['counts']['brokerOrders']}, bot orders {result['counts']['botOrders']}, "
             f"fill rows {result['counts']['fillRows']}, posted fee rows {result['counts']['feeRows']}, "
             f"FIFO round trips {result['counts']['roundTrips']}.", "",
             "## By strategy", "",
             "| Strategy | Orders | Filled | Partial | No fill | Rejected | Round trips | Gross realized | Est. fees | Est. net | Gross wins | Period |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in sorted(result["strategies"].items()):
        lines.append(f"| {name} | {s['orders']} | {s['filledOrders']} | {s['partiallyFilled']} | {s['canceledNoFill']} | "
                     f"{s['rejected']} | {s['roundTrips']} | {money(s['grossRealizedUsd'])} | {money(-s['estTakerFeesUsd'])} | "
                     f"{money(s['estNetRealizedUsd'])} | {s['grossWinningTrips']}/{s['roundTrips']} | "
                     f"{(s['first'] or '')[:10]} → {(s['last'] or '')[:10]} |")
    a = result["account"]
    lines += ["", "## Account-level paper result (bot scope)", "",
              f"- Fill cash flow: {money(a['fillCashFlowUsd'])}",
              f"- Open bot position marks: {money(a['openPositionMarksUsd'])}",
              f"- Posted USD fees: {money(a['postedUsdFees'])}",
              f"- **Net marked: {money(a['netMarkedUsd'])}**", "",
              "Estimated fees use the published 25 bps tier-1 taker rate per side and are labelled as estimates; "
              "posted fee rows carry no order ID, so they are only summarized.", "",
              "## Anomalies", ""]
    lines += [f"- {k}: {n}" for k, n in sorted(kinds.items())] or ["- none"]
    lines += ["", "Full detail: trade-audit.json, trades.csv, round-trips.csv. Paper fills are simulated; "
              "this is not live profitability."]
    (out / "TRADE-AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", help="credentials file (default: environment variables)")
    parser.add_argument("--snapshot", help="directory holding a saved broker-snapshot.json (offline)")
    parser.add_argument("--state-dir", help="bot state directory for ledger reconciliation")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    out = Path(args.output_dir)
    if args.snapshot:
        snapshot = json.loads((Path(args.snapshot) / "broker-snapshot.json").read_text(encoding="utf-8"))
    else:
        snapshot = fetch_snapshot(credentials_from(args.env), out / "raw")
    result = audit(snapshot, load_ledgers(Path(args.state_dir) if args.state_dir else None))
    write_reports(result, out)
    print((out / "TRADE-AUDIT.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
