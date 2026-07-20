"""
Stratégie de croisement de moyennes mobiles simples (SMA crossover).
Signal achat : MA courte > MA longue
Signal vente : MA courte < MA longue
"""

from __future__ import annotations

import pandas as pd
from loguru import logger

from config.settings import MA_SHORT, MA_LONG
from strategies.base_strategy import BaseStrategy


class MovingAverageStrategy(BaseStrategy):
    """Stratégie SMA Crossover.

    Args:
        short_window: Fenêtre de la moyenne mobile courte (défaut 20j).
        long_window: Fenêtre de la moyenne mobile longue (défaut 50j).
    """

    def __init__(
        self,
        short_window: int = MA_SHORT,
        long_window: int = MA_LONG,
    ) -> None:
        super().__init__(name=f"SMA({short_window}/{long_window})")
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Génère les signaux basés sur le croisement des moyennes mobiles.

        Args:
            df: DataFrame avec au moins une colonne "Close".

        Returns:
            Series de signaux : 1 (achat), -1 (vente), 0 (neutre).
        """
        if len(df) < self.long_window:
            logger.warning(
                f"[{self.name}] Pas assez de données ({len(df)} barres, "
                f"besoin de {self.long_window})."
            )
            return pd.Series(0, index=df.index)

        ma_short = df["Close"].rolling(self.short_window).mean()
        ma_long = df["Close"].rolling(self.long_window).mean()

        signals = pd.Series(0, index=df.index, dtype=int)
        signals[ma_short > ma_long] = 1
        signals[ma_short < ma_long] = -1

        # Les premières barres n'ont pas encore assez d'historique
        signals.iloc[: self.long_window - 1] = 0

        n_buy = (signals == 1).sum()
        n_sell = (signals == -1).sum()
        logger.debug(f"[{self.name}] Signaux générés : {n_buy} achats / {n_sell} ventes")
        return signals
