"""Tests unitaires pour le backtester et les métriques de performance."""

from __future__ import annotations

import pandas as pd
import pytest

from backtesting.backtester import Backtester
from backtesting.performance import compute_metrics
from strategies.moving_average_strategy import MovingAverageStrategy


class TestBacktester:
    def test_run_returns_dataframe(self, sample_ohlcv):
        strategy = MovingAverageStrategy(short_window=5, long_window=10)
        bt = Backtester(strategy, initial_capital=10_000.0)
        result = bt.run("TEST", sample_ohlcv)
        assert isinstance(result, pd.DataFrame)
        assert "equity" in result.columns

    def test_equity_length_matches_data(self, sample_ohlcv):
        strategy = MovingAverageStrategy(short_window=5, long_window=10)
        bt = Backtester(strategy, initial_capital=10_000.0)
        result = bt.run("TEST", sample_ohlcv)
        assert len(result) == len(sample_ohlcv)

    def test_equity_always_positive(self, sample_ohlcv):
        strategy = MovingAverageStrategy(short_window=5, long_window=10)
        bt = Backtester(strategy, initial_capital=10_000.0)
        result = bt.run("TEST", sample_ohlcv)
        assert (result["equity"] > 0).all()

    def test_equity_starts_near_initial_capital(self, sample_ohlcv):
        initial = 10_000.0
        strategy = MovingAverageStrategy(short_window=5, long_window=10)
        bt = Backtester(strategy, initial_capital=initial)
        result = bt.run("TEST", sample_ohlcv)
        # La première valeur doit être proche du capital initial
        assert abs(result["equity"].iloc[0] - initial) / initial < 0.10


class TestPerformanceMetrics:
    def _make_equity(self, values: list[float]) -> pd.DataFrame:
        dates = pd.date_range("2023-01-01", periods=len(values), freq="B")
        return pd.DataFrame(
            {"equity": values, "signal": [0] * len(values), "price": values},
            index=dates,
        )

    def test_positive_performance(self):
        equity = self._make_equity([10_000, 10_500, 11_000, 11_500])
        metrics = compute_metrics(equity, 10_000)
        assert metrics["performance_totale"] > 0

    def test_negative_performance(self):
        equity = self._make_equity([10_000, 9_500, 9_000, 8_500])
        metrics = compute_metrics(equity, 10_000)
        assert metrics["performance_totale"] < 0

    def test_max_drawdown_negative(self):
        equity = self._make_equity([10_000, 12_000, 8_000, 9_000])
        metrics = compute_metrics(equity, 10_000)
        assert metrics["drawdown_max"] < 0

    def test_metrics_keys_present(self):
        equity = self._make_equity([10_000, 10_100, 10_200])
        metrics = compute_metrics(equity, 10_000)
        expected_keys = {
            "capital_initial", "capital_final", "performance_totale",
            "drawdown_max", "sharpe_ratio", "nombre_trades", "taux_reussite_pct",
        }
        assert expected_keys.issubset(metrics.keys())
