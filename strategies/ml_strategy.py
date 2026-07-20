"""
Stratégie ML avec seuil de confiance — ne trade que quand le modèle est sûr.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import joblib
from loguru import logger

from config.settings import MODEL_STORE_DIR
from ml.feature_engineering import build_features
from strategies.base_strategy import BaseStrategy

CONFIDENCE_THRESHOLD = 0.58


class MLStrategy(BaseStrategy):
    def __init__(self, ticker: str, model_path: Path | None = None) -> None:
        super().__init__(name=f"ML({ticker})")
        self.ticker     = ticker
        self.model_path = model_path or MODEL_STORE_DIR / f"{ticker}_rf_model.joblib"
        self._model     = None
        self._mtime: float = 0.0
        self._feature_cols: list[str] | None = None

    def _load_model(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(f"Modèle introuvable : {self.model_path}")
        self._model = joblib.load(self.model_path)
        self._mtime = self.model_path.stat().st_mtime
        # Récupère les colonnes de features sélectionnées lors du training
        self._feature_cols = getattr(self._model, "_nexora_feature_cols", None)
        model_type = getattr(self._model, "_nexora_model_type", "ML")
        self.name = f"ML-{model_type}({self.ticker})"
        logger.info(f"[{self.name}] Modèle chargé | features={len(self._feature_cols) if self._feature_cols else 'all'}")

    def _ensure_fresh_model(self) -> None:
        if not self.model_path.exists():
            self._model = None
            return
        mtime = self.model_path.stat().st_mtime
        if self._model is None or mtime != self._mtime:
            self._load_model()

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        self._ensure_fresh_model()
        if self._model is None:
            return pd.Series(0, index=df.index)

        features = build_features(df)

        # Utilise uniquement les features sélectionnées à l'entraînement
        if self._feature_cols:
            available = [c for c in self._feature_cols if c in features.columns]
            features = features[available]

        valid_idx = features.dropna().index
        if valid_idx.empty:
            return pd.Series(0, index=df.index)

        X = features.loc[valid_idx]

        # Signaux basés sur la probabilité — trade uniquement si confiance >= seuil
        try:
            proba = self._model.predict_proba(X)[:, 1]
            signal_values = pd.Series(0, index=valid_idx, dtype=int)
            signal_values[proba >= CONFIDENCE_THRESHOLD]       =  1   # BUY fort
            signal_values[proba <= (1 - CONFIDENCE_THRESHOLD)] = -1   # SELL/SHORT fort
            # Expose la probabilité de la dernière décision pour le dashboard
            self._last_proba = float(proba[-1]) if len(proba) > 0 else 0.5
        except Exception:
            # Fallback sur predict classique si le modèle ne supporte pas predict_proba
            preds = self._model.predict(X)
            signal_values = pd.Series([1 if p == 1 else -1 for p in preds], index=valid_idx)
            self._last_proba = 0.5

        signals = pd.Series(0, index=df.index, dtype=int)
        signals.update(signal_values)

        n_buy  = (signals == 1).sum()
        n_sell = (signals == -1).sum()
        n_hold = (signals == 0).sum()
        logger.debug(f"[{self.name}] BUY={n_buy} SELL={n_sell} HOLD={n_hold} | seuil={CONFIDENCE_THRESHOLD:.0%}")
        return signals
