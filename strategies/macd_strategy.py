"""
Stratégie MACD (Moving Average Convergence Divergence).
Signal achat  : ligne MACD croise au-dessus de la ligne signal
Signal vente  : ligne MACD croise en-dessous de la ligne signal
"""

from __future__ import annotations

import pandas as pd
from loguru import logger

from strategies.base_strategy import BaseStrategy


class MACDStrategy(BaseStrategy):
    """Stratégie MACD crossover.

    Args:
        fast: Période EMA rapide (défaut 12).
        slow: Période EMA lente (défaut 26).
        signal: Période EMA du signal (défaut 9).
    """

    def __init__(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> None:
        super().__init__(name=f"MACD({fast},{slow},{signal})")
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        min_bars = self.slow + self.signal
        if len(df) < min_bars:
            logger.warning(f"[{self.name}] Pas assez de données ({len(df)} barres).")
            return pd.Series(0, index=df.index)

        close = df["Close"]
        ema_fast = close.ewm(span=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal, adjust=False).mean()

        # Position courante : MACD au-dessus du signal => long, en dessous => short
        above = (macd_line > signal_line).astype(int)
        signals = pd.Series(0, index=df.index, dtype=int)
        signals[above == 1] = 1
        signals[above == 0] = -1

        # Les premières barres (warmup) restent à 0
        signals.iloc[:min_bars] = 0

        n_buy = (signals == 1).sum()
        n_sell = (signals == -1).sum()
        logger.debug(f"[{self.name}] Signaux : {n_buy} achats / {n_sell} ventes")
        return signals
