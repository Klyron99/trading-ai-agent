"""
Moteur de backtesting : simule l'exécution d'une stratégie sur données historiques.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from loguru import logger

from config.settings import INITIAL_CAPITAL
from execution.order_manager import OrderManager
from execution.paper_broker import PaperBroker
from risk.risk_manager import RiskManager
from strategies.base_strategy import BaseStrategy


class Backtester:
    """Simule une stratégie sur un historique de prix."""

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: float = INITIAL_CAPITAL,
    ) -> None:
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.broker: PaperBroker | None = None

    def run(self, ticker: str, df: pd.DataFrame) -> pd.DataFrame:
        """Exécute le backtest et retourne la courbe du capital.

        Args:
            ticker: Symbole boursier.
            df: DataFrame OHLCV avec DatetimeIndex.

        Returns:
            DataFrame avec colonnes [equity, cash, signal, price], index=date.
        """
        logger.info(
            f"[Backtest] {self.strategy.name} sur {ticker} "
            f"({df.index[0].date()} → {df.index[-1].date()})"
        )

        self.broker = PaperBroker(initial_capital=self.initial_capital)
        risk_manager = RiskManager()
        order_manager = OrderManager(self.broker, risk_manager)

        signals = self.strategy.generate_signals(df)
        equity_curve: list[dict] = []

        for timestamp, row in df.iterrows():
            signal = int(signals.loc[timestamp])
            price = float(row["Close"])
            ts: datetime = (
                timestamp.to_pydatetime()
                if hasattr(timestamp, "to_pydatetime")
                else timestamp
            )

            order_manager.process_signal(ticker, signal, price, ts)

            pos = self.broker.get_position(ticker)
            position_value = pos.quantity * price if pos else 0.0
            equity = self.broker.cash + position_value

            equity_curve.append({
                "date": ts,
                "equity": equity,
                "cash": self.broker.cash,
                "signal": signal,
                "price": price,
            })

        result = pd.DataFrame(equity_curve).set_index("date")
        logger.success(
            f"[Backtest] Terminé. Capital final : {result['equity'].iloc[-1]:.2f} € "
            f"(initial : {self.initial_capital:.2f} €)"
        )
        return result
