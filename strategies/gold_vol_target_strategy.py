"""
Gold — exposition longue à volatilité ciblée (daily).

Issue de run_gold_backtest.py (GC=F 2000 → 2026, GLD 2004 → 2026) :
aucune règle de timing testée (SMA, croisement MM, momentum, Donchian,
RSI2) ne bat le simple buy & hold de l'or après frais en walk-forward.
La seule amélioration robuste sur les deux instruments est la gestion
de la taille : viser 12 % de volatilité annualisée réduit le drawdown
(hold-out 2021+ : -18 % au lieu de -25 %) à Sharpe égal ou meilleur.

Règle (aucun paramètre optimisé) :
    exposition = min(1, 12 % / volatilité réalisée 20 jours annualisée)
Calculée à la clôture, exécutée à l'ouverture suivante. Jamais de levier.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base_strategy import BaseStrategy


class GoldVolTargetStrategy(BaseStrategy):
    def __init__(self, target_vol: float = 0.12, vol_window: int = 20,
                 rebalance_threshold: float = 0.10) -> None:
        super().__init__("GoldVolTarget")
        self.target_vol = target_vol
        self.vol_window = vol_window
        # n'ajuste la position que si l'écart d'exposition dépasse ce seuil (limite les frais)
        self.rebalance_threshold = rebalance_threshold

    def target_exposure(self, df: pd.DataFrame) -> pd.Series:
        """Fraction du capital à investir en or (0 → 1)."""
        rv = df["Close"].pct_change().rolling(self.vol_window).std() * np.sqrt(252)
        return (self.target_vol / rv).clip(upper=1.0).fillna(0.0)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """+1 dès que la volatilité est connue (la stratégie est toujours longue) ;
        la taille vient de target_exposure()."""
        return (self.target_exposure(df) > 0).astype(int)

    def rebalance_needed(self, current_exposure: float, df: pd.DataFrame) -> bool:
        return abs(float(self.target_exposure(df).iloc[-1]) - current_exposure) > self.rebalance_threshold
