"""
Calcul des métriques de performance d'un backtest.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger


def compute_metrics(equity_curve: pd.DataFrame, initial_capital: float) -> dict:
    """Calcule les métriques clés de performance.

    Args:
        equity_curve: DataFrame avec colonnes equity, signal, price (index=date).
        initial_capital: Capital de départ.

    Returns:
        Dictionnaire de métriques.
    """
    equity = equity_curve["equity"]
    final_equity = equity.iloc[-1]
    total_return = (final_equity - initial_capital) / initial_capital

    # Drawdown maximum
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    # Rendements quotidiens
    daily_returns = equity.pct_change().dropna()
    mean_return = daily_returns.mean()
    std_return = daily_returns.std()

    # Sharpe ratio simplifié (sans taux sans risque, base annuelle 252j)
    sharpe = (mean_return / std_return * np.sqrt(252)) if std_return > 0 else 0.0

    # Statistiques sur les trades
    signals = equity_curve["signal"]
    trade_entries = (signals.diff() != 0) & (signals != 0)
    n_trades = trade_entries.sum()

    # Taux de réussite approximatif : jours avec signal=1 et rendement positif
    buy_days = equity_curve[equity_curve["signal"] == 1]
    if not buy_days.empty and len(buy_days) > 1:
        buy_returns = buy_days["equity"].pct_change().dropna()
        win_rate = (buy_returns > 0).mean()
    else:
        win_rate = 0.0

    metrics = {
        "capital_initial": initial_capital,
        "capital_final": round(final_equity, 2),
        "performance_totale": round(total_return * 100, 2),
        "drawdown_max": round(max_drawdown * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "nombre_trades": int(n_trades),
        "taux_reussite_pct": round(win_rate * 100, 2),
    }
    return metrics


def print_metrics(metrics: dict, strategy_name: str = "") -> None:
    """Affiche les métriques en console de façon lisible.

    Args:
        metrics: Dictionnaire retourné par compute_metrics().
        strategy_name: Nom de la stratégie pour l'en-tête.
    """
    sep = "─" * 45
    header = f"  Résultats — {strategy_name}  " if strategy_name else "  Résultats  "
    logger.info(f"\n{sep}\n{header}\n{sep}")
    logger.info(f"  Capital initial      : {metrics['capital_initial']:>10.2f} €")
    logger.info(f"  Capital final        : {metrics['capital_final']:>10.2f} €")
    logger.info(f"  Performance totale   : {metrics['performance_totale']:>+9.2f} %")
    logger.info(f"  Drawdown maximum     : {metrics['drawdown_max']:>+9.2f} %")
    logger.info(f"  Sharpe ratio         : {metrics['sharpe_ratio']:>10.3f}")
    logger.info(f"  Nombre de trades     : {metrics['nombre_trades']:>10}")
    logger.info(f"  Taux de réussite     : {metrics['taux_reussite_pct']:>9.2f} %")
    logger.info(sep)
