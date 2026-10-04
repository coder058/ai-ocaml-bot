# Murphy and candlestick chart work — actual evidence

## Active follow-up window

User requested six more hours on 2026-10-04. Follow-up scheduled every 30 minutes until 2026-10-05T00:29:46Z. This is an opportunity to continue work, not evidence of six hours of active development. Work inline, no subagents. Do not modify unrelated dirty files or Frankfurt/Fly Brain.

## Completed and verified so far

- Dublin runs the existing OCaml descriptive engine plus TA-Lib 0.8.1 C through Python. These are distinct implementations, not an OCaml port of TA-Lib.
- Installed catalog: 61 candlestick patterns and 113 indicator functions. Catalog is enumerated at runtime; every available pattern uses the installed C library's actual output and lookback.
- Sources: https://ta-lib.org/functions/ ; https://stockcharts.com/ten-laws/murphys-ten-laws.pdf . Pattern signed codes are not calibrated probabilities.
- Full contiguous closed-candle cache feeds analysis. Missing bars reset warmup. Real exchange calendar defines overnight equity adjacency. Invalid/open/future candles fail closed.
- TA-Lib warmup needs up to 101 bars from actual installed lookbacks. Seed transport now backfills when the cache has fewer than that.
- Chart payload includes up to 120 actual candles per frame, EMA20/50 overlays and actual library pattern events. This display cap is an uncalibrated presentation choice.
- Murphy checklist covers all ten laws with descriptive evidence and explicit partial/missing inputs. Support/resistance, confirmed-swing trendlines, retracements and seven exploratory chart geometries are calculated. Two-bar pivot confirmation and 5% range tolerance are UNCALIBRATED GUESSES.
- Six synthetic tests passed on Dublin (including compact forward evidence): all catalog outputs match C library, open/future/invalid reject, gap/session adjacency, confirmation causality and honest coverage. Six existing pipeline tests passed.
- Last sampled production scan: 91 markets x five frames = 455 chart slots, 450 with actual candles. No candles returned for FXB 1m/5m, FXC 1m, FXA 1m/5m on the IEX feed. Do not fabricate flat candles or call these charts populated.
- Monitor implementation adds all slots with lazy canvas painting, search/venue/frame filters and expanded TradingView Lightweight Charts. Web 26 tests, typecheck and production build passed. Browser QA verified 455 cards, five columns on desktop, 61 catalog rows, 113 indicator rows, search to EUR, interactive chart and ten Murphy law panels. Marker text clutter was removed; FX axis precision derives from actual OHLC values. Price rounding is display-only.
- Monitor broker history remains reset. `/api/live` retains only positions, `/api/export` remains 410. New `/api/markets` exposes market data only. No strategy/order/risk configuration changed.

## Remaining next steps (work these each follow-up)

1. Verify actual browser wall, filters, expansion, all candle catalog view, indicator view, timestamps and mobile layout. Fix presentation bugs; capture proof. Commit only scoped finished changes.
2. Measure actual feed/bar coverage by symbol/frame and investigate sparse IEX frames; improve real inputs rather than filling missing prices. Verify minute service cadence and exceptions after deployment.
3. Expand Murphy primary-trend context using real daily/weekly/monthly history where providers support it; record unavailable history and session alignment. Never treat 4h as a monthly trend.
4. Implement causal divergence and reversal/continuation geometry with explicit parameters and meaningful fixtures. Evaluate heuristics against labeled/chronological data before any order authority.
5. Add venue-appropriate volume/open interest, intermarket/breadth data only where licensed/public APIs actually provide it. Full Murphy book remains incomplete (Elliott, P&F, cycles and other discretionary modules).
6. Evaluate candidate patterns on chronological, point-in-time folds against unconditional/random-entry controls, realistic fees/slippage and multiple-testing limits. Existing short warmup snapshots are not a validated backtest or edge.
   `research/forward_pattern_audit.py` now provides first-observed gross movement labels with a frozen 21:00 UTC discovery/validation boundary. Run it at each follow-up using the exact command in `docs/FORWARD-PATTERN-AUDIT.md`; retain this attempt and report validation counts honestly. It has no execution/cost model and cannot authorize a policy.
7. Expand public market universe only from verified catalog; crypto trading stays BTC/ETH/SOL, Hyperliquid mainnet data-only, no real-money wallet, no invented spot FX. OANDA spot practice credentials missing; adapter unavailable.
8. Preserve hardcoded Alpaca paper endpoint, AAPL protection, durable pending-order reconciliation, $100 baseline and $500 BTC ceiling. Deploy a policy only if measured evidence justifies the engineering change; no forced trades to inflate counts.
9. At deadline delete automation `ai-ocaml-bot-seis-horas-de-an-lisis-y-gr-ficos`, report actual completed work and remaining limits. No promise of profit or breakthrough.

## Additional measured evidence

- A production scan at 18:34 UTC took 28.14 seconds. Frame states: 85 ready, 10 candidates, 11 stale, 4 warming, 340 regular-session closed, 5 without data. 401 frame suites had enough contiguous bars for all 61 catalog patterns. These figures are a snapshot, not a guarantee of subsequent health.
- Forward evidence now stores the last actual candle, all latest pattern/indicator values and concise geometry rather than repeating 120-candle histories. A production 1m record at 18:37:28 UTC was 8,206 bytes and had technicalEvidence with no technicalSuite history. The existing audit journal is preserved.
- Browser market projection removes repeated per-function parameters and unused swing history. Measured localhost response: 16,936,304 bytes, 2.31 seconds, 91 markets/455 slots. Full authoritative telemetry remains on disk, while market API response excludes broker orders/fills and position data.
- Read all ten HIP-3 dex metadata catalogs via official public info calls. Currency-token candidates only matched existing EUR/JPY/GBP and xyz:NOK; NOK must not be assumed FX (the symbol is also Nokia). No expansion or real-wallet action was performed based on ticker matching. New public catalog evidence is not a connected execution adapter.
- Optional practice FX account question is pending; user credentials must never be pasted into chat. Continue independent chart/data/evaluation work while waiting.
- Screenshot proof: local ignored file .local/murphy-eur-chart.png. Monitor broker history remains hidden and CSV endpoint 410.

## Verification completed at 18:55 UTC

- Public commit e9d7488 pushed; GitHub CI 37226169503 passed both jobs (OCaml build/unit tests, routing/connection boundaries, Python pattern/pipeline checks and web tests/typecheck/build).
- Provider concise annotations confirm xyz:EUR=EURUSD, xyz:JPY=USDJPY and xyz:GBP=GBPUSD under category fx. xyz:NOK is category stocks, display NOK, keywords Nokia/telecom. No FX expansion from false ticker matching.
- Historical SIP entitlement tested read-only for sparse FX ETF charts, using end at least 15 minutes old as Alpaca's Market Data FAQ specifies. Actual 2026-10-01 onward response counts: 1m FXA 29, FXB 18, FXC 69; 5m FXA 27, FXB 17, FXC 52. These are sparse trade bars, not a continuous spot-FX feed. No main cache/feed changed; no missing minute candles invented. Next work should separate chart history from contiguous indicator warmup, and keep IEX/SIP provenance explicit instead of mixing volume streams.
- Browser expansion verified on desktop and normal 561px viewport. Normal layout uses horizontal frame strips, no page overflow. All 455 chart cards remain accessible; expanded dialog shows ten Murphy panels, 61 catalog rows, 113 indicator rows and true OHLCV readout. Saved proof .local/murphy-eur-chart.png.
- The current full market projection measured 16.94 MB / 2.31 s locally. Further reduction should be driven by measured client memory and latency, not guessed performance claims.

## Gap correction verified at 19:07 UTC

- Seven Murphy tests passed on Dublin. Chart history now preserves actual earlier candles across missing bars; indicators, geometry and pattern warmup still use only the latest contiguous segment. Earlier EMA entries remain null and no synthetic candles are inserted.
- Production scan at 19:05 UTC completed in 37.10 seconds with no retrieval errors. BTC 1m displayed 120 actual bars but only seven consecutive bars; ETH 1m/5m had one. This is a real data limitation, not 120 usable indicator observations.
- Local production build passed and the monitor was restarted. Browser verified BTC 1m: 120 actual candles, eight consecutive observations on the subsequent scan, visible data-gap warning, and unavailable EMA50. Broker history remains hidden.

## Forward audit first run and catalog evidence

- Six point-in-time adversarial tests passed locally and on Dublin. Audit rejects unfinished candles, missing future horizon bars, revised earliest features and labels crossing the temporal boundary. Comparison baseline uses the same venue/symbol/frame/fold; no order authority, net P&L or calibrated probability.
- Frozen attempt: one wholly future candle, split 2026-10-04T21:00:00Z. Both are explicitly uncalibrated research design choices, set before this first report. Signed pattern direction is also an uncalibrated hypothesis, including indecision formations.
- Actual first run: 282,626,053-byte prefix, SHA-256 `18e2e7a130be36b2f7912b34edc614dae3511cfb5dac94c622230adc27583d51`; 199,419 journal lines, 197,061 older lines without technical candle features, 2,358 unique eligible technical candles. Feature observation range 17:08:27–19:10:37 UTC on 2026-10-04. Do not pretend the older records contained these features.
- 1,780 gross labels, all discovery, 951 exploratory pattern comparisons. Rejections: 220 signal states not ready, 358 missing future horizon candles. Validation remains empty before the frozen boundary; these gross labels exclude execution costs and do not establish an edge. Full private report `/home/ubuntu/jsbot-paper-state/forward-pattern-audit.json`; reproducible method in docs/FORWARD-PATTERN-AUDIT.md.
- Official xyz metadata verified `xyz:DXY` and `xyz:KRW` each have `isDelisted=true`. EUR/GBP/JPY have no delisted flag; NOK is Nokia, not a currency pair. No fake expansion performed.
