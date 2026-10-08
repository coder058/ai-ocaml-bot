"""Causality and cost accounting of research/cost_aware_backtest.py on synthetic bars."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research'))
try:
    import pandas as pd
    import cost_aware_backtest as cab
except ImportError:  # pragma: no cover - optional research dependency
    cab = None


@unittest.skipIf(cab is None, 'requires pandas (research/requirements-backtest.txt)')
class CostAwareBacktest(unittest.TestCase):
    def dataset(self, closes):
        index = pd.date_range('2020-01-01', periods=len(closes), freq='D')
        bars = pd.DataFrame({'Open': closes, 'High': closes, 'Low': closes, 'Close': closes}, index=index)
        return cab.Dataset('synthetic', bars, pd.Series(0.0, index=index), 252.0, 'equity_etf', 'daily')

    def test_signal_earns_only_the_next_bar(self):
        # Price doubles on bar 3 only. A weight set on bar 3 itself must not earn it.
        ds = self.dataset([1, 1, 1, 2, 2, 2])
        same_bar = pd.Series([0, 0, 0, 1, 0, 0], index=ds.bars.index, dtype=float)
        prior_bar = pd.Series([0, 0, 1, 0, 0, 0], index=ds.bars.index, dtype=float)
        r_same = cab.evaluate(ds, same_bar, '2020-01-01', '2020-12-31', 0.0)
        r_prior = cab.evaluate(ds, prior_bar, '2020-01-01', '2020-12-31', 0.0)
        self.assertAlmostEqual(r_same['net_cagr'], 0.0, places=12)  # doubling not captured
        self.assertGreater(r_prior['net_cagr'], 1.0)

    def test_costs_charged_per_unit_turnover(self):
        ds = self.dataset([1.0] * 11)
        flip = pd.Series([i % 2 for i in range(11)], index=ds.bars.index, dtype=float)
        result = cab.evaluate(ds, flip, '2020-01-01', '2020-12-31', 25.0)
        # Flat prices: the only P&L is cost. Ten held bars, entering from cash, alternate 0/1.
        self.assertAlmostEqual(result['gross_cagr'], 0.0, places=12)
        self.assertLess(result['net_cagr'], 0.0)
        self.assertAlmostEqual(result['turnover_per_year'], 9 / (10 / 252))  # 9 changes over 10 bars

    def test_holdout_is_not_opened_by_default(self):
        parser_default = cab.main.__code__.co_consts
        self.assertIn('develop,validate', parser_default)


if __name__ == '__main__':
    unittest.main()
