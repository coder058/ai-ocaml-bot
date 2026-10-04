"""Read-only BTC paper ledger audit; never submits, cancels or replaces orders."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))

import export_telemetry  # noqa: E402
from paper_fee_activity_check import fee_count  # noqa: E402
from paper_fill_cash_flow import reconcile  # noqa: E402


def audit() -> dict:
    credentials = export_telemetry.read_env(export_telemetry.ENV_PATH)
    service = export_telemetry.service_state(credentials)
    events, journal_complete, decision_events = export_telemetry.journal()
    document = export_telemetry.snapshot(credentials, service, events,
                                         journal_complete, decision_events)
    flows = reconcile(document)
    activities = [fee_count(kind, credentials) for kind in ("CFEE", "FEE")]
    bot_orders = [order for order in document["orders"]
                  if str(order.get("clientOrderId", "")).startswith("jsbotbtc")
                  and order.get("symbol") in ("BTCUSD", "BTC/USD")]
    trace_ids = set(document["decisionHistory"])
    position = next((item for item in document["positions"]
                     if item.get("symbol") in ("BTCUSD", "BTC/USD")), None)
    return {
        **flows,
        "ordersComplete": document["ordersComplete"],
        "fillsComplete": document["fillsComplete"],
        "journalComplete": document["journalComplete"],
        "journalEventsRead": len(events),
        "botOrdersWithDecisionTrace": sum(order.get("id") in trace_ids
                                           for order in bot_orders),
        "botOrdersWithoutDecisionTrace": sum(order.get("id") not in trace_ids
                                              for order in bot_orders),
        "btcBrokerPosition": None if position is None else {
            "qty": position.get("qty"), "marketValue": position.get("marketValue"),
            "avgEntryPrice": position.get("avgEntryPrice")},
        "feeActivities": activities,
        "feeAttribution": "unverified; account fee activities are not matched to bot fills",
        "netResultVerified": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
