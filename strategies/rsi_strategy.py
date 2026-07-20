"""
Stratégie RSI (Relative Strength Index).
Signal achat  : RSI < seuil_bas (zone survente)
Signal vente  : RSI > seuil_haut (zone surachat)
Signal neutre : entre les deux seuils
"""

from __future__ import annotations

import pandas as pd
from loguru import logger

from ml.feature_engineering import compute_rsi
from strategies.base_strategy import BaseStrategy


class RSIStrategy(BaseStrategy):
    """Stratégie RSI mean-reversion.

    Args:
        period: Période du RSI (défaut 14).
        oversold: Seuil de survente — signal BUY en dessous (défaut 30).
        overbought: Seuil de surachat — signal SELL au-dessus (défaut 70).
    """

    def __init__(
        self,
        period: int = 14,
        oversold: int = 30,
        overbought: int = 70,
    ) -> None:
        super().__init__(name=f"RSI({period},{oversold}/{overbought})")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        if len(df) < self.period + 1:
            logger.warning(f"[{self.name}] Pas assez de données ({len(df)} barres).")
            return pd.Series(0, index=df.index)

        rsi = compute_rsi(df["Close"], window=self.period)

        signals = pd.Series(0, index=df.index, dtype=int)
        signals[rsi < self.oversold] = 1
        signals[rsi > self.overbought] = -1

        n_buy = (signals == 1).sum()
        n_sell = (signals == -1).sum()
        logger.debug(f"[{self.name}] Signaux : {n_buy} achats / {n_sell} ventes")
        return signals
