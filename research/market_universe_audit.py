"""Read-only inventory of the paper account's tradable market candidates.

This uses the hardcoded Alpaca paper origin via the existing exporter adapter.
It prints no credentials, balances, account identifiers, or order data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))

from export_telemetry import ENV_PATH, paper_get, read_env  # noqa: E402


def summarize(assets: list[dict], requested: dict[str, dict]) -> dict:
    tradable = [asset for asset in assets if asset.get("tradable") is True
                and asset.get("status") == "active"]
    usd_pairs = sorted(str(asset.get("symbol")) for asset in tradable
                       if str(asset.get("symbol", "")).endswith("/USD"))
    return {
        "source": "Alpaca paper /v2/assets read-only",
        "activeTradableCryptoPairs": len(tradable),
        "activeTradableUsdCryptoPairs": len(usd_pairs),
        "usdCryptoSymbols": usd_pairs,
        "equityProxies": requested,
        "performanceCapacityMeasured": False,
        "probabilitiesCalibrated": False,
    }


def main() -> None:
    credentials = read_env(ENV_PATH)
    assets = paper_get("/v2/assets?status=active&asset_class=crypto", credentials)
    if not isinstance(assets, list):
        raise ValueError("crypto asset catalog was not an array")
    # SOURCE: DIA is a Dow-tracking ETF; XLE and XOP are energy-sector ETFs.
    # These are proxies, not the cash Dow index or physical energy prices.
    proxies = {}
    for symbol in ("DIA", "XLE", "XOP"):
        asset = paper_get(f"/v2/assets/{symbol}", credentials)
        if not isinstance(asset, dict):
            raise ValueError(f"{symbol} asset response was not an object")
        proxies[symbol] = {
            "status": asset.get("status"),
            "tradable": asset.get("tradable"),
            "fractionable": asset.get("fractionable"),
            "assetClass": asset.get("class"),
        }
    print(json.dumps(summarize(assets, proxies), indent=2))


if __name__ == "__main__":
    main()
