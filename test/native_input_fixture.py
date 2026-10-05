"""Real frozen OCaml replay with synthetic candles and fake broker transport."""
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
from decision_inputs import attach

ENGINE = ROOT / "_build/default/bin/analyze_frames_main.exe"
MINUTES = {"1m": 1, "5m": 5, "30m": 30, "1h": 60, "4h": 240}


def document(root, symbol, venue, frame):
    now = datetime.now(timezone.utc)
    at = now.replace(second=0, microsecond=0)
    minutes = MINUTES[frame]
    boundary = int(at.timestamp()) // (minutes*60) * minutes*60
    stamp = lambda dt: dt.isoformat().replace("+00:00", "Z")
    rows = []
    # SOURCE: 100 deterministic synthetic bars exceed the existing EMA50 warmup;
    # price/volume values are test data, not parameters or market observations.
    for index in range(100):
        close = 90.1 + index / 10
        rows.append({"t": stamp(datetime.fromtimestamp(boundary-(100-index)*minutes*60, timezone.utc)),
                     "o": close+.01, "h": close+.02, "l": close-1, "c": close, "v": 1})
    original = {"symbol": symbol, "venue": venue,
        "frames": {f: rows if f == frame else [] for f in MINUTES},
        "fetches": {frame: {"retrievedAt": stamp(now)}}}
    payload = {"asOf": stamp(at), "markets": [original]}
    result = json.loads(subprocess.check_output([str(ENGINE)], input=json.dumps(payload).encode()))
    engine_sha = hashlib.sha256(ENGINE.read_bytes()).hexdigest()
    engine_copy = root / "frozen-analyzers" / (engine_sha + ".exe")
    engine_copy.parent.mkdir(exist_ok=True)
    if not engine_copy.exists():
        shutil.copy2(ENGINE, engine_copy)
    # SOURCE: explicit synthetic extension identity; native policy is real OCaml.
    extension_sha = hashlib.sha256(b"synthetic descriptive extension fixture").hexdigest()
    attach(result, [original], root/"decision-inputs", engine_sha, extension_sha)
    result["retrievedAt"] = stamp(now)
    return result
