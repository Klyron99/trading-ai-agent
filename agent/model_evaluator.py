"""
Évalue si un nouveau modèle ML est meilleur que l'ancien avant de le remplacer.
Comparaison sur : drawdown, performance totale, stabilité (Sharpe), nombre de trades.
"""

from __future__ import annotations

from loguru import logger

from backtesting.backtester import Backtester
from backtesting.performance import compute_metrics
from config.settings import INITIAL_CAPITAL


def _score(metrics: dict) -> float:
    """Score composite (plus haut = meilleur modèle)."""
    sharpe  = max(metrics.get("sharpe_ratio", 0), 0)
    perf    = metrics.get("performance_totale", 0)
    dd      = abs(metrics.get("drawdown_max", 100))      # pénalité drawdown
    n_tr    = metrics.get("nombre_trades", 0)
    wr      = metrics.get("taux_reussite_pct", 0)

    return (
        0.30 * sharpe
        + 0.25 * (perf / 10)          # normalisé ~ 0-1 pour 10 % perf
        + 0.20 * (wr / 100)
        - 0.15 * (dd / 20)            # pénalité si dd > 20 %
        + 0.10 * min(n_tr / 50, 1.0)  # bonus trades jusqu'à 50
    )


def evaluate_model(
    old_strategy,
    new_strategy,
    ticker: str,
    df,
) -> tuple[bool, dict, dict]:
    """Compare deux stratégies ML sur les mêmes données.

    Returns:
        (new_is_better, old_metrics, new_metrics)
    """
    bt_old = Backtester(old_strategy, initial_capital=INITIAL_CAPITAL)
    bt_new = Backtester(new_strategy, initial_capital=INITIAL_CAPITAL)

    ec_old = bt_old.run(ticker, df)
    ec_new = bt_new.run(ticker, df)

    m_old = compute_metrics(ec_old["equity"], INITIAL_CAPITAL)
    m_new = compute_metrics(ec_new["equity"], INITIAL_CAPITAL)

    s_old = _score(m_old)
    s_new = _score(m_new)

    new_is_better = s_new > s_old

    logger.info(
        f"[ModelEvaluator] {ticker} — "
        f"ancien score={s_old:.3f} | nouveau score={s_new:.3f} | "
        f"{'REMPLACÉ ✓' if new_is_better else 'CONSERVÉ'}"
    )

    return new_is_better, m_old, m_new
