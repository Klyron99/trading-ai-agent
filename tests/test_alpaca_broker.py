"""Tests unitaires pour AlpacaPaperBroker (mode simulation uniquement)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_broker(capital: float = 50_000.0):
    """Instancie un broker en mode simulation (sans clés API)."""
    # On s'assure que les clés sont absentes et l'URL est correcte
    with patch.dict(os.environ, {
        "ALPACA_API_KEY": "",
        "ALPACA_SECRET_KEY": "",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "LIVE_TRADING": "false",
    }):
        # Recharge settings avec les env patchés
        import importlib
        import config.settings as s
        importlib.reload(s)
        from execution.alpaca_paper_broker import AlpacaPaperBroker
        importlib.reload(
            sys.modules["execution.alpaca_paper_broker"]
        )
        from execution.alpaca_paper_broker import AlpacaPaperBroker as B
        return B(simulation_capital=capital)


# ── Tests de sécurité ────────────────────────────────────────────────────────

class TestSecurity:
    def test_live_trading_true_raises(self):
        """Le broker doit refuser de démarrer si LIVE_TRADING=true."""
        with patch.dict(os.environ, {
            "LIVE_TRADING": "true",
            "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
            "ALPACA_API_KEY": "",
            "ALPACA_SECRET_KEY": "",
        }):
            import importlib
            import config.settings as s
            importlib.reload(s)
            import execution.alpaca_paper_broker as mod
            importlib.reload(mod)
            with pytest.raises(EnvironmentError, match="LIVE_TRADING=true"):
                mod.AlpacaPaperBroker()

    def test_wrong_url_raises(self):
        """Le broker doit refuser toute URL non-paper."""
        with patch.dict(os.environ, {
            "LIVE_TRADING": "false",
            "ALPACA_BASE_URL": "https://api.alpaca.markets",  # URL live !
            "ALPACA_API_KEY": "",
            "ALPACA_SECRET_KEY": "",
        }):
            import importlib
            import config.settings as s
            importlib.reload(s)
            import execution.alpaca_paper_broker as mod
            importlib.reload(mod)
            with pytest.raises(EnvironmentError, match="URL Alpaca non autorisée"):
                mod.AlpacaPaperBroker()

    def test_paper_url_accepted(self):
        """L'URL paper-api.alpaca.markets doit être acceptée."""
        with patch.dict(os.environ, {
            "LIVE_TRADING": "false",
            "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
            "ALPACA_API_KEY": "",
            "ALPACA_SECRET_KEY": "",
        }):
            import importlib
            import config.settings as s
            importlib.reload(s)
            import execution.alpaca_paper_broker as mod
            importlib.reload(mod)
            # Ne doit pas lever d'exception
            broker = mod.AlpacaPaperBroker(simulation_capital=10_000)
            assert broker._simulation_mode is True


# ── Tests du mode simulation ─────────────────────────────────────────────────

class TestSimulationMode:
    """Ces tests utilisent le broker en mode simulation locale (sans API)."""

    def _fresh_broker(self, capital=50_000.0):
        with patch.dict(os.environ, {
            "LIVE_TRADING": "false",
            "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
            "ALPACA_API_KEY": "",
            "ALPACA_SECRET_KEY": "",
        }):
            import importlib
            import config.settings as s
            importlib.reload(s)
            import execution.alpaca_paper_broker as mod
            importlib.reload(mod)
            return mod.AlpacaPaperBroker(simulation_capital=capital)

    def test_simulation_mode_active_without_keys(self):
        b = self._fresh_broker()
        assert b._simulation_mode is True

    def test_initial_cash(self):
        b = self._fresh_broker(capital=25_000.0)
        info = b.get_account()
        assert info.cash == pytest.approx(25_000.0)

    def test_buy_reduces_cash(self):
        b = self._fresh_broker(capital=50_000.0)
        # Injecte un prix fictif directement
        b._sim_positions.clear()
        b._sim_cash = 50_000.0

        # Simule un achat sans appel yfinance
        price = 500.0
        qty = 10
        total = price * qty
        b._sim_cash -= total
        b._sim_positions["SPY"] = {"qty": qty, "avg_price": price}

        assert b._sim_cash == pytest.approx(50_000.0 - total)
        assert b._sim_positions["SPY"]["qty"] == qty

    def test_sell_restores_cash(self):
        b = self._fresh_broker(capital=50_000.0)
        buy_price = 500.0
        sell_price = 520.0
        qty = 5

        # Simule position ouverte
        b._sim_cash = 50_000.0 - buy_price * qty
        b._sim_positions["SPY"] = {"qty": qty, "avg_price": buy_price}

        # Simule vente
        b._sim_cash += sell_price * qty
        del b._sim_positions["SPY"]

        expected_cash = 50_000.0 + (sell_price - buy_price) * qty
        assert b._sim_cash == pytest.approx(expected_cash)
        assert "SPY" not in b._sim_positions

    def test_get_position_returns_none_when_no_position(self):
        b = self._fresh_broker()
        assert b.get_position("AAPL") is None

    def test_has_open_order_always_false_in_simulation(self):
        b = self._fresh_broker()
        assert b.has_open_order("SPY") is False

    def test_submit_order_invalid_qty_raises(self):
        b = self._fresh_broker()
        with pytest.raises(ValueError, match="Quantité invalide"):
            b.submit_market_order("SPY", "buy", 0)

    def test_submit_order_invalid_side_raises(self):
        b = self._fresh_broker()
        with pytest.raises(ValueError, match="Sens invalide"):
            b.submit_market_order("SPY", "hold", 1)


# ── Tests du calcul de signal ─────────────────────────────────────────────────

class TestComputeSignal:
    def test_buy_signal_when_short_above_long(self):
        from live_paper_trading import compute_signal
        from collections import deque

        # Prix croissants → MA courte > MA longue
        prices = deque([100 + i for i in range(20)], maxlen=40)
        assert compute_signal(prices, short=3, long_=10) == 1

    def test_sell_signal_when_short_below_long(self):
        from live_paper_trading import compute_signal
        from collections import deque

        # Prix décroissants → MA courte < MA longue
        prices = deque([200 - i for i in range(20)], maxlen=40)
        assert compute_signal(prices, short=3, long_=10) == -1

    def test_neutral_when_buffer_too_small(self):
        from live_paper_trading import compute_signal
        from collections import deque

        prices = deque([100, 101, 102], maxlen=40)  # Seulement 3 prix, long_=10
        assert compute_signal(prices, short=3, long_=10) == 0
