"""
Gestionnaire d'ordres : fait le lien entre les signaux, le risk manager et le broker.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from execution.paper_broker import PaperBroker
from risk.risk_manager import OrderRequest, RiskManager


class OrderManager:
    """Orchestre l'envoi des ordres après validation du risque."""

    def __init__(self, broker: PaperBroker, risk_manager: RiskManager) -> None:
        self.broker = broker
        self.risk_manager = risk_manager

    def process_signal(
        self,
        ticker: str,
        signal: int,
        price: float,
        timestamp: datetime,
    ) -> None:
        """Traite un signal et envoie l'ordre si le risque est acceptable.

        Args:
            ticker: Symbole boursier.
            signal: 1 (achat), -1 (vente), 0 (neutre).
            price: Prix actuel.
            timestamp: Date du signal.
        """
        if signal == 0 or price <= 0:
            return

        portfolio_value = self.broker.get_portfolio_value()

        if signal == 1:
            qty = self.risk_manager.compute_position_size(price, portfolio_value)
            if qty <= 0:
                return

            order = OrderRequest(
                ticker=ticker,
                side="buy",
                price=price,
                quantity=qty,
                portfolio_value=portfolio_value,
                cash=self.broker.cash,
            )
            valid, reason = self.risk_manager.validate(order)
            if valid:
                self.broker.buy(ticker, qty, price, timestamp)
            else:
                logger.debug(f"[{ticker}] Achat bloqué : {reason}")

        elif signal == -1:
            position = self.broker.get_position(ticker)
            if position is None:
                return

            if self.risk_manager.check_stop_loss(position.avg_price, price):
                logger.info(f"[{ticker}] Stop loss déclenché @ {price:.2f}")

            self.broker.sell(ticker, position.quantity, price, timestamp)
