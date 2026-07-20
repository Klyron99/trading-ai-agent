"""
Boucle d'apprentissage : télécharge les données, réentraîne le modèle ML,
évalue s'il est meilleur que l'ancien, sélectionne la meilleure stratégie
et met à jour la mémoire de l'agent.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf
from loguru import logger

from agent import memory as mem
from agent.model_evaluator import evaluate_model
from agent.strategy_selector import select_best_strategy
from config.settings import (
    AGENT_ALLOWED_TICKERS,
    AGENT_RETRAIN_EVERY_HOURS,
    DATA_START_DATE,
    MODEL_STORE_DIR,
)
from ml.feature_engineering import build_features
from ml.train_model import train
from strategies.ml_strategy import MLStrategy


_CRYPTO = {"BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"}

def _download(ticker: str) -> "pd.DataFrame":
    from data.market_data import download_ohlcv
    # Crypto : horaire (24h/7j = ~17 000 bougies sur 720j)
    # Actions/ETF : journalier depuis 2015 (marché fermé la nuit, peu de bougies horaires)
    if ticker in _CRYPTO:
        return download_ohlcv(ticker, interval="1h", use_cache=False)
    else:
        return download_ohlcv(ticker, start="2015-01-01", interval="1d", use_cache=False)


def _log_self_improvement(ticker: str) -> None:
    """Analyse les trades réels et affiche le win rate pour suivi."""
    try:
        outcomes = mem.get_trade_outcomes(ticker, limit=100)
        if not outcomes:
            return
        wins = sum(1 for t in outcomes if t["win"])
        total = len(outcomes)
        wr = wins / total
        avg_pnl = sum(t["pnl_pct"] for t in outcomes if t["pnl_pct"] is not None) / total
        logger.info(
            f"[SelfImprove] {ticker} — {total} trades réels | "
            f"WR={wr:.1%} | P&L moyen={avg_pnl:.2%}"
        )
        # Si win rate réel < 45% sur 20+ trades → alerte
        if total >= 20 and wr < 0.45:
            logger.warning(
                f"[SelfImprove] {ticker} WR réel {wr:.1%} < 45% — réentraînement prioritaire"
            )
    except Exception as exc:
        logger.debug(f"[SelfImprove] {exc}")


def retrain_ticker(ticker: str) -> dict:
    """Réentraîne le modèle pour un ticker. Retourne un rapport."""
    logger.info(f"[LearningLoop] Début réentraînement {ticker}")
    _log_self_improvement(ticker)

    df = _download(ticker)
    if df.empty:
        raise ValueError(f"Aucune donnée pour {ticker}")

    features_df = build_features(df)
    if features_df.empty:
        raise ValueError(f"Features vides pour {ticker}")

    # Modèle existant (pour comparaison)
    model_path = MODEL_STORE_DIR / f"{ticker}_rf_model.joblib"
    old_model_exists = model_path.exists()

    # Entraîne le nouveau modèle
    new_model = train(df, ticker)

    # Évalue si le nouveau modèle est meilleur
    replaced = True
    if old_model_exists:
        try:
            old_strat = MLStrategy(ticker)  # charge l'ancien modèle depuis disque
            # rechargement temporaire : on sauvegarde d'abord le nouveau
            import joblib
            tmp_path = MODEL_STORE_DIR / f"{ticker}_rf_model_new.joblib"
            joblib.dump(new_model, tmp_path)

            # stratégie wrappant le nouveau modèle
            class _TmpMLStrategy:
                name = "ML-new"
                def __init__(self, m): self._m = m
                def generate_signals(self, df):
                    from ml.feature_engineering import build_features, build_target
                    feat = build_features(df).dropna()
                    if feat.empty: return __import__("pandas").Series(0, index=df.index)
                    preds = self._m.predict(feat)
                    import pandas as pd
                    sig = pd.Series(0, index=df.index)
                    sig[feat.index] = (preds * 2 - 1)
                    return sig

            new_strat_tmp = _TmpMLStrategy(new_model)
            better, m_old, m_new = evaluate_model(old_strat, new_strat_tmp, ticker, df)
            tmp_path.unlink(missing_ok=True)

            if not better:
                # Restaure l'ancien modèle (train() a déjà écrasé le fichier)
                import joblib as jl
                jl.dump(old_strat._model, model_path)
                replaced = False
                logger.info(f"[LearningLoop] {ticker} — ancien modèle conservé")
        except Exception as exc:
            logger.warning(f"[LearningLoop] Comparaison échouée ({exc}) — nouveau modèle conservé")

    # Sélectionne la meilleure stratégie et log dans la mémoire
    best_name, _, all_scores = select_best_strategy(ticker, df)

    for s in all_scores:
        mem.log_strategy_performance(
            ticker=ticker,
            strategy=s["strategy"],
            sharpe=s["sharpe"],
            perf_pct=s["perf_pct"],
            drawdown_pct=s["drawdown_pct"],
            win_rate_pct=s["win_rate_pct"],
            n_trades=s["n_trades"],
            score=s["score"],
        )

    acc        = getattr(new_model, "_nexora_accuracy",   0.0)
    model_type = getattr(new_model, "_nexora_model_type", "GradientBoosting")
    mem.log_model(ticker, model_type, accuracy=acc, replaced=replaced)

    report = {
        "ticker":       ticker,
        "ts":           datetime.utcnow().isoformat(),
        "replaced":     replaced,
        "best_strategy": best_name,
        "strategy_scores": all_scores,
    }
    logger.info(f"[LearningLoop] {ticker} terminé — best={best_name} replaced={replaced}")
    return report


def run_learning_loop(tickers: list[str] | None = None) -> None:
    """Lance le cycle de réentraînement pour tous les tickers autorisés."""
    mem.init_db()
    tickers = tickers or AGENT_ALLOWED_TICKERS

    for ticker in tickers:
        try:
            retrain_ticker(ticker)
        except Exception as exc:
            logger.error(f"[LearningLoop] {ticker} erreur : {exc}")

    logger.info(
        f"[LearningLoop] Cycle terminé. Prochain dans {AGENT_RETRAIN_EVERY_HOURS}h."
    )
