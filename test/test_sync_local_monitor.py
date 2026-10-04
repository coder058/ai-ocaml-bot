"""A failed SSH projection must not destroy the last usable local snapshot."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
from sync_local_monitor import fetch_snapshot, validate_snapshot  # noqa: E402


def document() -> dict:
    # SOURCE: synthetic rows exercise transport/projection guards, not returns.
    return {"version": 1, "source": "Dublin OCaml paper service",
            "generatedAt": "2026-10-01T21:00:00Z", "positions": [],
            "orders": [], "fills": [], "journal": [], "ordersComplete": True,
            "fillsComplete": True, "journalComplete": False}


class LocalSyncTests(unittest.TestCase):
    def test_stock_projection_requires_exact_owned_scope_and_excludes_aapl(self):
        data=document();data['orders']=[{'symbol':'QQQ','clientOrderId':'aibotstkExample'}]
        data['positions']=[{'symbol':'QQQ'}];self.assertEqual(validate_snapshot(data),data)
        data['positions'].append({'symbol':'AAPL'})
        with self.assertRaises(ValueError):validate_snapshot(data)
    def test_new_paper_crypto_requires_its_own_lab_order_scope(self):
        data = document()
        data["orders"] = [{"symbol": "ETHUSD", "clientOrderId": "jsbotmtfexample"}]
        data["positions"] = [{"symbol": "ETH/USD"}]
        self.assertEqual(validate_snapshot(data), data)
        data["positions"].append({"symbol": "SOLUSD"})
        with self.assertRaises(ValueError):
            validate_snapshot(data)

    def test_full_snapshot_is_retained_and_ssh_never_posts_an_order(self):
        data = document()
        # SOURCE: repeat enough journal bytes to exceed the existing 1 MiB
        # Vercel ingestion guard; local file mode must keep the full history.
        data["journal"] = [{"at": data["generatedAt"], "message": "x" * 1_048_577}]
        body = json.dumps(data).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.json"
            with patch("sync_local_monitor.subprocess.run", return_value=
                       subprocess.CompletedProcess([], 0, body, b"")) as run:
                fetch_snapshot(path, "known-host", Path("private-key"))
            self.assertEqual(json.loads(path.read_bytes()), data)
            arguments = run.call_args.args[0]
            self.assertIn("StrictHostKeyChecking=yes", arguments)
            self.assertEqual(arguments[-1], "sudo -n python3 -")
            remote_script = run.call_args.kwargs["input"].decode()
            self.assertNotIn(".main(", remote_script)
            self.assertNotIn(".sign(", remote_script)
            self.assertNotIn("method=", remote_script)

    def test_remote_failure_or_invalid_json_preserves_last_good_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.json"
            previous = json.dumps(document()).encode()
            path.write_bytes(previous)
            for result, error in ((subprocess.CompletedProcess([], 1, b"", b""), RuntimeError),
                                  (subprocess.CompletedProcess([], 0, b"bad json", b""), ValueError)):
                with patch("sync_local_monitor.subprocess.run", return_value=result):
                    with self.assertRaises(error):
                        fetch_snapshot(path, "known-host", Path("private-key"))
                self.assertEqual(path.read_bytes(), previous)

    def test_changed_projection_cannot_export_private_holdings(self):
        data = document()
        data["positions"] = [{"symbol": "AAPL", "qty": "private"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.json"
            with patch("sync_local_monitor.subprocess.run", return_value=
                       subprocess.CompletedProcess([], 0, json.dumps(data).encode(), b"")):
                with self.assertRaises(ValueError):
                    fetch_snapshot(path, "known-host", Path("private-key"))
            self.assertFalse(path.exists())

    def test_optional_market_analysis_never_claims_broker_authority_or_probability(self):
        data = document()
        data["marketPipeline"] = {"orderAuthority": False, "winProbability": None,
                                  "markets": [{"symbol": "xyz:EUR", "venue": "Hyperliquid HIP-3", "frames": {}}]}
        self.assertEqual(validate_snapshot(data), data)
        data["marketPipeline"]["orderAuthority"] = True
        with self.assertRaises(ValueError):
            validate_snapshot(data)


if __name__ == "__main__":
    unittest.main()
