"""
Broker simulé pour le paper trading.
AUCUN ordre réel n'est jamais envoyé.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from loguru import logger

from config.settings import INITIAL_CAPITAL


@dataclass
class Position:
    """Représente une position ouverte."""

    ticker: str
    quantity: int
    avg_price: float
    opened_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_price


@dataclass
class Order:
    """Représente un ordre exécuté dans le paper broker."""

    ticker: str
    side: str
    quantity: int
    price: float
    timestamp: datetime
    pnl: float = 0.0

    @property
    def value(self) -> float:
        return self.quantity * self.price


class PaperBroker:
    """Simule un courtier pour le paper trading. N'envoie JAMAIS d'ordres réels."""

    def __init__(self, initial_capital: float = INITIAL_CAPITAL) -> None:
        self.cash: float = initial_capital
        self.initial_capital: float = initial_capital
        self.positions: dict[str, Position] = {}
        self.order_history: list[Order] = []

    def get_portfolio_value(self, current_prices: dict[str, float] | None = None) -> float:
        """Valeur totale cash + positions (au prix actuel si fourni, sinon prix d'achat moyen)."""
        if current_prices:
            positions_value = sum(
                p.quantity * current_prices.get(p.ticker, p.avg_price)
                for p in self.positions.values()
            )
        else:
            positions_value = sum(p.cost_basis for p in self.positions.values())
        return self.cash + positions_value

    def buy(self, ticker: str, quantity: int, price: float, timestamp: datetime) -> bool:
        """Simule un achat. Retourne True si l'ordre a été exécuté."""
        total_cost = quantity * price
        if total_cost > self.cash:
            logger.warning(
                f"[PAPER] Achat refusé {ticker} x{quantity} @ {price:.2f} "
                f"(coût {total_cost:.2f} > cash {self.cash:.2f})"
            )
            return False

        self.cash -= total_cost

        if ticker in self.positions:
            pos = self.positions[ticker]
            total_qty = pos.quantity + quantity
            pos.avg_price = (pos.cost_basis + total_cost) / total_qty
            pos.quantity = total_qty
        else:
            self.positions[ticker] = Position(
                ticker=ticker,
                quantity=quantity,
                avg_price=price,
                opened_at=timestamp,
            )

        order = Order(
            ticker=ticker, side="buy", quantity=quantity,
            price=price, timestamp=timestamp,
        )
        self.order_history.append(order)
        logger.info(
            f"[PAPER BUY]  {ticker} x{quantity} @ {price:.2f} "
            f"| Cash restant : {self.cash:.2f}"
        )
        return True

    def sell(self, ticker: str, quantity: int, price: float, timestamp: datetime) -> bool:
        """Simule une vente. Retourne True si l'ordre a été exécuté."""
        pos = self.positions.get(ticker)
        if pos is None or pos.quantity < quantity:
            logger.warning(
                f"[PAPER] Vente refusée {ticker} x{quantity} : position insuffisante."
            )
            return False

        pnl = (price - pos.avg_price) * quantity
        self.cash += quantity * price
        pos.quantity -= quantity
        if pos.quantity == 0:
            del self.positions[ticker]

        order = Order(
            ticker=ticker, side="sell", quantity=quantity,
            price=price, timestamp=timestamp, pnl=pnl,
        )
        self.order_history.append(order)
        logger.info(
            f"[PAPER SELL] {ticker} x{quantity} @ {price:.2f} "
            f"| PnL : {pnl:+.2f} | Cash : {self.cash:.2f}"
        )
        return True

    def get_position(self, ticker: str) -> Optional[Position]:
        return self.positions.get(ticker)

    def summary(self) -> dict:
        return {
            "cash": self.cash,
            "positions": {
                t: {"qty": p.quantity, "avg_price": p.avg_price}
                for t, p in self.positions.items()
            },
            "total_orders": len(self.order_history),
            "total_pnl": sum(o.pnl for o in self.order_history if o.side == "sell"),
        }
