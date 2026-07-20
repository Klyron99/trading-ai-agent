"""Tests unitaires pour le gestionnaire de risque."""

from __future__ import annotations

import pytest

from risk.risk_manager import OrderRequest, RiskManager


@pytest.fixture
def risk_manager() -> RiskManager:
    return RiskManager(risk_per_trade=0.01, max_position_size=0.20, stop_loss_pct=0.05)


class TestRiskManager:
    def test_valid_buy_order(self, risk_manager):
        order = OrderRequest(
            ticker="AAPL",
            side="buy",
            price=150.0,
            quantity=5,
            portfolio_value=10_000.0,
            cash=5_000.0,
        )
        valid, reason = risk_manager.validate(order)
        assert valid is True
        assert reason == ""

    def test_insufficient_cash(self, risk_manager):
        # 5 actions * 150 € = 750 € < 20% de 10 000 € (OK en taille)
        # mais cash disponible = 100 € → refusé pour cash insuffisant
        order = OrderRequest(
            ticker="AAPL",
            side="buy",
            price=150.0,
            quantity=5,
            portfolio_value=10_000.0,
            cash=100.0,
        )
        valid, reason = risk_manager.validate(order)
        assert valid is False
        assert "Cash insuffisant" in reason

    def test_position_too_large(self, risk_manager):
        order = OrderRequest(
            ticker="AAPL",
            side="buy",
            price=150.0,
            quantity=20,          # 20 * 150 = 3 000 € > 20 % de 10 000
            portfolio_value=10_000.0,
            cash=10_000.0,
        )
        valid, reason = risk_manager.validate(order)
        assert valid is False
        assert "Position trop grande" in reason

    def test_sell_order_always_valid(self, risk_manager):
        order = OrderRequest(
            ticker="AAPL",
            side="sell",
            price=150.0,
            quantity=10,
            portfolio_value=10_000.0,
            cash=0.0,
        )
        valid, reason = risk_manager.validate(order)
        assert valid is True

    def test_compute_position_size_positive(self, risk_manager):
        qty = risk_manager.compute_position_size(price=100.0, portfolio_value=10_000.0)
        assert qty > 0

    def test_stop_loss_triggered(self, risk_manager):
        assert risk_manager.check_stop_loss(entry_price=100.0, current_price=94.0) is True

    def test_stop_loss_not_triggered(self, risk_manager):
        assert risk_manager.check_stop_loss(entry_price=100.0, current_price=97.0) is False

    def test_unknown_side_rejected(self, risk_manager):
        order = OrderRequest(
            ticker="AAPL",
            side="hold",
            price=150.0,
            quantity=1,
            portfolio_value=10_000.0,
            cash=5_000.0,
        )
        valid, reason = risk_manager.validate(order)
        assert valid is False
        assert "inconnu" in reason.lower()
