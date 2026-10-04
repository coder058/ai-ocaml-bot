# Local monitor operations

## Start on Windows

From the repository root, run `./deploy/start_local_monitor.ps1` in PowerShell.
The launcher builds Next.js, requires a successful initial SSH snapshot, then
starts the web server and background synchronization worker. It requires the
existing Dublin SSH key, Python, Node.js, and installed web dependencies.

Open **http://127.0.0.1:3000** on this computer. The server binds to loopback;
this address is not a public portfolio URL. Both local processes must be
restarted after a computer restart. The paper bot continues on Dublin when the
local monitor is closed or the computer is off.

## Data path

- The SSH worker invokes the deployed read-only broker snapshot functions.
  Alpaca credentials remain on Dublin. No order request is made by this worker.
- Only the sanitized lab-scoped crypto/stock projection is accepted. The
  monitor excludes AAPL and unrelated holdings and has no order control.
- Each successful fetch replaces `.local/telemetry.json` atomically. Failed
  fetches preserve the previous file and its original timestamp.
- Synchronization waits 60 seconds between completed fetches. The measured
  full broker fetch adds further time; this is not a real-time fill UI. The display polls the local API every fifteen
  seconds. A new display poll does not fetch new broker data.
- The local ingestion endpoint returns HTTP 405. Local snapshots never use
  Vercel Blob storage. Runtime JSON, logs, and PID files are Git-ignored.

## Historical verification on 2026-10-01

The first automatic background fetch completed at `21:24:16.367313Z`, after
the initial launcher fetch. The local API served that same snapshot with
`Cache-Control: no-store`: 1,537 orders and 2,451 fill activity rows. These are
broker records, not counts of profitable trades. Broker order and fill history
completeness flags were true; journal completeness was false.

The production build, TypeScript check, twelve web tests, and three SSH worker
tests passed. The listener was verified at `127.0.0.1:3000`. The UI showed the
execution history, entry/exit filtering, order reasons, and provisional paper
accounting. Posted fees can lag; paper execution does not establish live
profitability.

The obsolete `ai-ocaml-telemetry.timer` on Dublin was stopped and disabled to end
Vercel uploads. `ai-ocaml-telemetry.service` was stopped; its previous failed marker
was cleared. `jsbot-paper.service` remained active and enabled. Trading policy,
order sizing, and account credentials were unchanged.

## Current desk

See [the trading desk guide](TRADING-DESK.md) and [4 October connection evidence](CONNECTIONS-AND-MONITOR-WORK.md). The P&L curve records actual snapshots while the local API is polled. Its local file survives a restart, but no observations are fabricated while the monitor is closed.

## Positions-only reset (2026-10-04)

The current monitor displays only bot-owned open broker positions, current exposure and unrealized P&L. Past orders, fills, closed trades, realized P&L and the historical performance curve are removed from the UI and `/api/live` response. History CSV exports return HTTP 410. This supersedes the history UI described earlier in this document.

The original complete `.local/telemetry.json`, performance journal and Dublin broker/OMS journals remain intact for reconciliation and auditing. The display reset does not reset the broker account, change strategies, submit/cancel orders or close positions. Each refreshed full snapshot is projected to the same positions-only response; a restart or synchronization cannot restore the history view.

Verified: 25 web tests, TypeScript check and production build passed. Local HTTP response retained BTC/USD and SOL/USD inventory, omitted historical arrays and performance, and the export endpoint returned 410. Browser verification confirmed only the current positions view.
