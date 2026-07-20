"""
Classe de base abstraite pour toutes les stratégies de trading.
Toute nouvelle stratégie doit hériter de BaseStrategy et implémenter generate_signals().
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseStrategy(ABC):
    """Interface commune pour les stratégies de trading.

    Une stratégie reçoit un DataFrame OHLCV et retourne une Series de signaux :
        +1  → acheter
        -1  → vendre
         0  → neutre
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Calcule les signaux de trading à partir des données de marché.

        Args:
            df: DataFrame OHLCV avec DatetimeIndex.

        Returns:
            Series d'entiers (-1, 0, 1) alignée sur l'index de df.
        """
        ...

    def __repr__(self) -> str:
        return f"<Strategy: {self.name}>"
