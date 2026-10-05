# Development and service freeze — 2026-10-05

The owner replaced this project's backlog with [Event Desk](https://github.com/coder058/event-desk).
The former strategy/FX/technical-analysis backlog is frozen. Code, capture files,
ownership journals and broker accounting history remain intact.

Before stopping services, a fresh authenticated Alpaca paper read found no open
orders and only protected/unowned AAPL. No liquidation or credential rotation was
performed. A second broker read after the shutdown found the same state.

Disabled and stopped ten project timers: FX connection, stock paper scheduler,
stock quote/session audits, five-minute bars, market pipeline, Markov shadow,
multi-paper, multiframe shadow and telemetry. Stopped their associated services.
Disabled and stopped order capture, stock capture, public Hyperliquid capture and
market capture. Four capture services and all timers verified inactive; some
oneshot services retain systemd failed status. They are not running and their
failure markers were not cleared to conceal diagnostic history.

Exact unit states are retained privately on the VPS at
`/etc/eventdesk/old-service-state.json`. The local old monitor can display retained
snapshots; its historical data is not a claim that collection is still active.

Unrelated services and Frankfurt research were not changed. Restarting the old
executors requires a separate owner decision and fresh ownership/order reconciliation.

