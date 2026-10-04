# Hyperliquid HIP-3 public capture

`research/hyperliquid_capture.py` records a single `allMids` subscription to
the `xyz` perp dex plus BBO and 1m candle updates for 14 named contracts. It
has no wallet, exchange SDK, secret, private account channel or order function.
The paper executor remains on its hardcoded Alpaca paper endpoint.

## Instrument scope

The chosen contracts are `xyz:EUR`, `xyz:JPY`, `xyz:GBP`, `xyz:XYZ100`,
`xyz:SP500`, `xyz:TSLA`, `xyz:NVDA`, `xyz:AAPL`, `xyz:MSFT`, `xyz:AMZN`,
`xyz:GOOGL`, `xyz:META`, `xyz:AMD` and `xyz:BRENTOIL`. They are perpetual
contracts. EUR/JPY/GBP are FX-like market names; confirm the reference/oracle
specification before displaying them as conventional spot currency pairs.
The three are not ten FX pairs. XYZ100/SP500 are derivatives, not cash index
prices. Equity perps do not convey ownership of shares. Contracts may change
status; refresh and validate the `xyz` universe before relying on an allowlist.

At the initial feed check, 29 subscriptions were acknowledged. `allMids`
contained 126 symbol keys, and each of the selected contracts emitted BBO and
candle updates during the measured capture window. These observations do not
establish simultaneous executable liquidity, uninterrupted delivery, a
benchmark under load or order permission.

## Archive and operations

The process writes locally received messages as JSONL gzip, one file per UTC
hour and connection session, under
`/home/ubuntu/jsbot-paper-state/hyperliquid-capture/`. The legacy uncompressed
daily JSONL file from before hourly compression remains as-is. File writes
carry local receipt nanoseconds, session ID and a per-session sequence. `bbo`
and `allMids` have no exchange timestamp in this stored envelope. A candle
update can be revised; it is evidence only after its declared close time was
already in the past at the recorded receipt time. The raw feed is private and
is not included in public telemetry.

The service is `ai-ocaml-hyperliquid-capture.service`. Read-only status commands:

```sh
systemctl status ai-ocaml-hyperliquid-capture.service
journalctl -u ai-ocaml-hyperliquid-capture.service -n 30 --no-pager
.venv/bin/python research/hyperliquid_capture_health.py
```

The health report counts received messages by channel and selected symbol,
local sessions, sequence gaps in locally archived records and malformed
lines. It cannot observe messages that the provider never sent or prove a
remote sequence had no omissions. An hourly gzip file that is still open has
no final trailer; the scanner reads its flushed records and lists it in
`incompleteGzipFiles`. After normal rotation or service shutdown, the file
should be complete. If it remains incomplete after the writer has stopped,
treat it as a truncated archive and investigate it.

## First run and correction

The initial plain JSONL collector closed its handle at each reconnect but kept
the date marker. When the same date resumed, it skipped opening the file and
stopped with `AssertionError`. It restarted twice. The dated archive reached
about 200 MB during the first capture; it was retained unchanged. The process
now resets file state at session boundaries and writes compressed hourly
files with unique session IDs. A service restart re-acknowledged all 29
subscriptions; the health scan parsed both legacy and gzip files with zero
corrupt lines and zero gaps in the sequence numbers that were archived.

The current file is independent of `hlbot/capture/ws.py`, whose older recorder
supports core-perp trades, BBO and context at much wider symbol coverage. That
recorder taught useful lessons about one-writer locking, subscribe-time replay,
sequence/dedup and clock offsets. Do not treat its historical 531-subscription
test as a performance measurement for this HIP-3 process.

## Limits and next work

- This service currently stores BBO and candle messages; it does not reconstruct
  a full L2 order book or derive Murphy/Pattern Forge features.
- Candle subscriptions are trade driven; a missing update is not a fabricated
  flat candle. Add an explicit close scheduler and as-of revision handling
  before using these files as continuous bars.
- BBO has no exchange timestamp in this subscription format; receipt time alone
  cannot establish venue-to-host latency. Calibrate clock offset for timestamped
  trades before reporting network latency.
- The health scanner currently reads an entire UTC day's files. Keep an eye on
  its runtime and memory as captures accumulate. Rotate/compressing reduces disk
  use, but retention has not yet been defined.
- Next: validate contract metadata, add integrity-preserving retention, derive
  per-market freshness/spread/coverage snapshots, then test a deterministic
  replay against the same archived byte stream. Keep order authority disabled.

References: [Hyperliquid WebSocket subscriptions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions),
[HIP-3 builder-deployed perps](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals).
