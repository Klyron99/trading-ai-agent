"""Tests unitaires pour les stratégies de trading."""

from __future__ import annotations

import pandas as pd
import pytest

from strategies.moving_average_strategy import MovingAverageStrategy


class TestMovingAverageStrategy:
    def test_returns_series_same_length(self, sample_ohlcv):
        strategy = MovingAverageStrategy(short_window=5, long_window=10)
        signals = strategy.generate_signals(sample_ohlcv)
        assert isinstance(signals, pd.Series)
        assert len(signals) == len(sample_ohlcv)

    def test_signals_are_valid_values(self, sample_ohlcv):
        strategy = MovingAverageStrategy(short_window=5, long_window=10)
        signals = strategy.generate_signals(sample_ohlcv)
        assert set(signals.unique()).issubset({-1, 0, 1})

    def test_first_n_bars_are_zero(self, sample_ohlcv):
        long_window = 20
        strategy = MovingAverageStrategy(short_window=10, long_window=long_window)
        signals = strategy.generate_signals(sample_ohlcv)
        assert (signals.iloc[: long_window - 1] == 0).all()

    def test_insufficient_data_returns_zeros(self):
        strategy = MovingAverageStrategy(short_window=20, long_window=50)
        tiny_df = pd.DataFrame(
            {"Close": [100.0] * 30},
            index=pd.date_range("2023-01-01", periods=30, freq="B"),
        )
        signals = strategy.generate_signals(tiny_df)
        assert (signals == 0).all()

    def test_buy_signal_when_short_above_long(self):
        """Vérifie qu'un signal achat est généré quand MA courte > MA longue."""
        strategy = MovingAverageStrategy(short_window=3, long_window=5)
        # Prix croissants → MA courte finit au-dessus de MA longue
        prices = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
        df = pd.DataFrame(
            {"Close": prices},
            index=pd.date_range("2023-01-01", periods=len(prices), freq="B"),
        )
        signals = strategy.generate_signals(df)
        assert signals.iloc[-1] == 1

    def test_sell_signal_when_short_below_long(self):
        """Vérifie qu'un signal vente est généré quand MA courte < MA longue."""
        strategy = MovingAverageStrategy(short_window=3, long_window=5)
        prices = [19, 18, 17, 16, 15, 14, 13, 12, 11, 10]
        df = pd.DataFrame(
            {"Close": prices},
            index=pd.date_range("2023-01-01", periods=len(prices), freq="B"),
        )
        signals = strategy.generate_signals(df)
        assert signals.iloc[-1] == -1
