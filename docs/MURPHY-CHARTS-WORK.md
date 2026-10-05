# Murphy and candlestick chart work — actual evidence

## Active follow-up window

User extended the request to at least eight hours starting 2026-10-04T19:36:49Z and inline continuation until engineering readiness. The minimum boundary is 2026-10-05T03:36:49Z, a readiness review rather than automatic completion. Follow-up scheduling is a backup, not evidence of active development. See EXECUTION-TRACE-WORK.md for actual subsequent work. Work inline, no subagents. Preserve unrelated dirty files and Frankfurt/Fly Brain.

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
3. Native daily/weekly context is connected for the 72 monitored Alpaca instruments and all 19 public HIP-3 instruments (actual final seed receipt 2026-10-05T01:23:14Z). HIP-3 uses its verified Thursday weekly grid; 18 weekly series still lack EMA50 warmup. See PRIMARY-TREND-CONTEXT.md, MARKET-PIPELINE.md and EXECUTION-TRACE-WORK.md. Continue monthly/short-history coverage with real data and closure calendars. Never treat 4h as a monthly trend.
4. Causal latest-price-swing RSI/MACD divergences now have fixtures, as do double tops/bottoms and head-and-shoulders/inverse. Implement remaining reversal/continuation geometry and independently matched oscillator pivots with explicit parameters. Evaluate these exploratory heuristics against chronological data before any order authority.
5. Add venue-appropriate volume/open interest, intermarket/breadth data only where licensed/public APIs actually provide it. Full Murphy book remains incomplete (Elliott, P&F, cycles and other discretionary modules).
6. Evaluate candidate patterns on chronological, point-in-time folds against unconditional/random-entry controls, realistic fees/slippage and multiple-testing limits. Existing short warmup snapshots are not a validated backtest or edge.
   `research/forward_pattern_audit.py` now provides first-observed gross movement labels with a frozen 21:00 UTC discovery/validation boundary. Run it at each follow-up using the exact command in `docs/FORWARD-PATTERN-AUDIT.md`; retain this attempt and report validation counts honestly. It has no execution/cost model and cannot authorize a policy.
7. Expand public market universe only from verified catalog; crypto trading stays BTC/ETH/SOL, Hyperliquid mainnet data-only, no real-money wallet, no invented spot FX. OANDA spot practice credentials missing; adapter unavailable.
8. Preserve hardcoded Alpaca paper endpoint, AAPL protection, durable pending-order reconciliation, $100 baseline and $500 BTC ceiling. Deploy a policy only if measured evidence justifies the engineering change; no forced trades to inflate counts.
9. At the minimum eight-hour boundary review actual readiness and remaining work. Delete automation `ai-ocaml-bot-seis-horas-de-an-lisis-y-gr-ficos` only on engineering readiness or when no independent useful work remains without missing external input. Do not claim hours worked, profit or breakthrough from elapsed time.

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

## Swing warnings and data diagnosis

- Nine Murphy tests passed on Dublin. Additional fixtures cover actual neckline-close requirements for double top/bottom and head-and-shoulders/inverse, positive/negative momentum comparisons, finite inputs and the right-hand confirmation candle. Warnings cannot appear before that confirming candle closes.
- RSI/MACD divergences sample the indicator at the latest two confirmed price pivots. This is an explicitly uncalibrated heuristic, not independently matched oscillator swing points or a validated trade strategy. `confirmationCloseAt` identifies historical candle maturity; `evaluatedAsOf` identifies this current scan. Forward journal `observedAt` remains actual receipt time.
- Live scan at 19:17 UTC took 27.76 seconds, no errors, 170 descriptive divergence warnings across existing chart data. These include old/closed-session formations, not 170 new actionable signals. All retain orderAuthority=false.
- Short-warmup Murphy panels now show warming/waiting_swings and per-indicator availability rather than empty descriptive values. Full book remains incomplete.
- Read-only two-hour crypto history comparison at approximately 19:17 UTC returned BTC 94, ETH 15 and SOL 41 actual minute bars. None filled missing timestamps in the current cache. Observed holes therefore persist in the same provider's historical response; no flat/synthetic candles inserted, no claim that a transport restart fixes sparse trades.
- Public CI passed for both chart-gap commit be053f7 and audit commit 33d6b54. Divergence changes are checked separately before publication.

## Preview payload refinement

- Wall response now retains every chart's actual candles, EMA overlays, latest detected pattern codes and one actual marker per detection candle. Full per-instrument details are fetched only when opened, including every pattern event, all indicator outputs and Murphy panels. Broker history is still excluded.
- Same 19:24 UTC local snapshot serialization: full payload 17,664,926 bytes; preview 7,409,453 bytes; 58.06% reduction computed from those byte counts. This measures JSON size, not broker latency, throughput or HFT execution performance.
- 27 web tests passed, including preview/detail preservation and exclusion of private broker fields. Production build/typecheck passed after fixing a null detail-state check.
- Browser verified the EUR 1h detail, ten Murphy panels, all 61 catalog rows, 113 indicator rows and 239 actual catalog detections across the displayed candles. Historical divergence confirmation close and current evaluation are separately visible. Restored all 455 cards after verification; proof `.local/murphy-current-monitor.png`.
- Actual HTTP check: preview 7,410,027 bytes / 2.46 seconds with 91 markets; expanded response contained one instrument and full analysis. Partial selector returns 400; unknown instrument returns 404. Payload reduction did not demonstrate a latency improvement versus the earlier 2.31-second sample; these are individual requests, not a controlled latency benchmark.
- Public CI passed for divergence commit 6fa8170. Preview changes are deployed on localhost; scoped commit and CI complete this milestone. Six-hour follow-up remains active until 00:29:46 UTC; elapsed time is not active development evidence.
- Preview commit d3cfc0d pushed and CI 37228667711 passed both jobs (OCaml build/tests, Python routing/connection/pattern/pipeline/audit checks, web 27 tests/typecheck/build). Last verified Dublin scan 19:32 UTC: 91 products, 455 slots, 450 populated charts, 27.33 seconds and no errors. Pipeline timer and three capture/execution services checked active. Unrelated dirty files are preserved.

## Native and current public context — 5 October 01:54 UTC

- All 19 monitored HIP-3 daily/weekly histories were received by 01:23 UTC. Daily contexts descriptive; XYZ100 has 51 closed weeks, the other 18 weekly series remain warming. Actual provider Thursday boundaries are shown, no fabricated EMA50/monthly completion.
- Current public OI, funding, provider day volume and mark/oracle fields now display in law 10 with actual HTTP receipt. Provider observation time is unavailable; native precision is retained without USD/annualization assumptions. One current observation does not complete historical volume/OI confirmation, so law 10 stays partial.
- Actual 01:54 scan had 19 descriptive current contexts, 91 products/455 slots and no errors. EUR 1h browser verified real values/receipt/limits. Five adapter, nine Murphy, eight pipeline and 38 frontend tests passed; production build/typecheck passed. Documentation and tests disclose public-data-only authority. No policy promoted; full Murphy methodology and net executable validation remain incomplete.

## Native monthly Alpaca context — 5 October 05:24 UTC

- Verified actual provider 1Month responses at 02:46:58–59 UTC for QQQ/NVDA and BTC, 53 periods including open October. Added calendar-month closure, New York DST/leap/year-rollover handling, actual broker-calendar membership and missing-month warmup resets. Requested 52 native months from existing EMA50/previous/leading-period requirements, not a fabricated 30-day aggregation.
- Monthly stock prices/volume explicitly use documented split adjustment as retrieved; existing daily/weekly remain raw. Each frame retains actual source, adjustment, as-of and response receipt. These scales are not silently combined as one adjusted return series or point-in-time corporate-action evidence. Historical first-observed journal rows remain untouched; no execution rule changed.
- Production cached 04:52:13–23 UTC: 72 monthly summaries, 71 descriptive, SOL warming. QQQ/NVDA/BTC each 52 consecutive closed periods; October excluded. HIP-3 monthly remains unavailable. Law 1 remains partial; corrected its obsolete blanket monthly-missing wording without claiming full book methodology.
- Nine native tests locally/Dublin, seven HIP-3, eight pipeline and nine Murphy regressions on Dublin passed; 40 frontend tests and production build/typecheck passed. Browser QQQ 1h verified monthly dates, actual EMA20/50, source/split adjustment and real individual receipts. At configured 970/480 widths, document and each card scroll widths matched client widths. Restored normal size and all 455 charts. Screenshot .local/monthly-native-context-proof.png.
- Wall-clock gap after the 02:50 checks until the 05:20 continuation is not active engineering evidence. The 03:36 minimum review boundary passed during that gap; actual readiness review follows at the current time, without backdating completion or claiming eight active hours.

## Native HIP-3 30-day context — 5 October 08:03 UTC

- Actual public EUR/XYZ100 probes at 07:46 confirmed provider `1M` means fixed 30-day epoch blocks. Added explicit `Native1M` context, validated t/T boundaries, open-block withholding, missing-grid warmup resets and budgeted staggered collection. Alpaca calendar-month handling remains separate.
- Actual cache: 11/19 instruments seeded at 08:03, all warming; EUR ten and XYZ100 twelve closed blocks, last September 4 to October 4. No fabricated EMA50, calendar months, spot FX or broker fills. Law 1 and full Murphy remain partial.
- Ten adapter tests locally/Dublin, nine pipeline/nine Murphy on Dublin; 45 frontend tests and production build/typecheck passed. Browser EUR 1h verified dates/receipt/30-day label and unavailable averages. A narrow native filter select exceeded its allocated label; constrained that actual select rather than hiding page overflow. Final updated browser verification follows.
- Stock protocol 0c9fcf2 passed both CI jobs 37279393380. Open-session stock quotes/validation, exact cohort fee allocation, practice FX credentials and execution, HIP-3 execution and demonstrated edge remain incomplete. No strategy activation or eight-active-hours claim.
