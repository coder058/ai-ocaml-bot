# Frozen Markov shadow evaluation

The existing BTC/USD five-minute model records a descriptive probability of a
higher next native bar close. It cannot authorize orders. This is a finite-state
statistical model, not a calibrated probability of winning a trade.

`research/score_markov_shadow.py` now validates every prediction, including
unlabeled ones: exact frozen training counts/state/fallback/probability, aware
receipt times, actual snapshot reception, aligned bars and prospective forecast
window. A label must follow its prediction in the journal, arrive after the next
close and agree with both retained closes, direction and movement arithmetic.
Decreasing receipt order, duplicate events, future data and nonfinite values
fail closed. The CLI freezes one actual journal prefix and saves model, scorer
and journal hashes; unfinished final appends are ignored and disclosed.

## Reproduce on Dublin

```sh
cd /home/ubuntu/ocaml-paper-market-lab
sudo -n .venv/bin/python research/score_markov_shadow.py \
  research/models/markov-2026h1.json \
  /home/ubuntu/jsbot-paper-state/markov-shadow.jsonl \
  --output /home/ubuntu/jsbot-paper-state/markov-shadow-score.json
```

This reads already captured data. It does not train/change the model or submit
orders. Seven adversarial tests passed locally and on Dublin Python 3.10; the
actual retained journal also passed the strengthened checks. Public CI runs
these tests. Raw captures/journals remain private.

## Actual frozen report — 2026-10-05 01:29:38 UTC

| Observation | Measured value |
| --- | --- |
| Predictions / scored labels / unlabeled | 2,079 / 2,075 / 4 |
| Markov Brier | 0.2495878133768393 |
| Frozen training-base-rate Brier | 0.2500061879068083 |
| Mean directional native bar-close movement | 0.4247093462236366 bps |
| Prediction lead, min / median / max | 3.525722 / 293.705553 / 299.494861 seconds |
| Directional closes above the published T1 linearized fee-only hurdle | 4 |

The training cutoff is 1 July 2026; that historical data was retrieved on
27 September, so it is historical as retrieved, not a point-in-time training
dataset. Raw deployed model SHA-256:
`c5ba22a1be9a455f283e9dd32ab8867d202421438f4c60c9d54b9df9292e99c0`.
The preserved local formatting differs from Git's raw model bytes, but decoded
models were verified equal, with common sorted/compact JSON SHA-256
`9604f797e9287f86254da95953824ec9a1c6c275e0219d91a350e57e9abb29c5`.
The unrelated model file was not modified or committed.

Frozen journal: 1,690,242 bytes, SHA-256
`6ae63c0556393776780cf5a7564a913c8c48b3da874d39843f0d1fba1304112b`.
Scorer SHA-256:
`b83a749a5ab5c0f98b39daf9eb0f9b7d97520ef75ef49ccea32b0d1fe00d3d84`.

## Limits

Lower Brier measures squared error of bar-close direction; this small observed
difference does not prove calibration, significance or edge. Outcomes are
serially dependent, lead times differ and unlabeled forecasts are not discarded
as wins. The legacy journal field `forwardMidpointBps` is retained without
rewriting history, but output names now say **native bar close**: Alpaca crypto
bars can contain trades and quote midpoint prices, not a verified pure midpoint.
[Alpaca documents the bar construction](https://docs.alpaca.markets/us/docs/historical-crypto-data-1).

The 50 bps hurdle is only the linearized sum of two published T1 taker fees;
the account tier is unverified, and it excludes spread, received-asset
compounding, size, latency, partial fills and execution. It is not net P&L.
[Published crypto fees](https://docs.alpaca.markets/us/docs/crypto-fees).
The mean native price movement is far below that conditional fee-only hurdle.
No policy was activated. Paper/shadow results do not establish live profitability.

The 01:29:38 artifact is preserved at
`/home/ubuntu/jsbot-paper-state/markov-shadow-score-20261005T012938.json`.
After removing redundant repeated label checks (every prediction already has
those checks), the final deployed scorer passed the actual journal again at
01:34:46 UTC: 2,080 predictions / 2,076 scored / four unlabeled, Brier
0.24961307193721485 versus base 0.2500063792738566, mean directional close
movement 0.4192077702215121 bps. Journal prefix 1,691,051 bytes, SHA-256
`b482f2c15e7ead5d913efad06cac4cc22d3b1359ad25813a96540a9d2d4d47ba`;
final scorer SHA-256
`882b868bf7b223cb2e1d9dd44db135abdafc89cb73b0cffd168811f395d3ea6e`.
The saved latest report uses that exact deployed source. These additional labels
do not change the policy decision or remove the stated limits.
