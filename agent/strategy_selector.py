"""
Sélectionne automatiquement la meilleure stratégie pour un ticker donné.
Lance un backtest sur toutes les stratégies disponibles et les classe par score composite.
"""

from __future__ import annotations

from loguru import logger

from backtesting.backtester import Backtester
from backtesting.performance import compute_metrics
from config.settings import INITIAL_CAPITAL
from strategies.macd_strategy import MACDStrategy
from strategies.ml_strategy import MLStrategy
from strategies.moving_average_strategy import MovingAverageStrategy
from strategies.rsi_strategy import RSIStrategy


def _score(metrics: dict) -> float:
    sharpe  = max(metrics.get("sharpe_ratio", 0), 0)
    perf    = metrics.get("performance_totale", 0)
    dd      = abs(metrics.get("drawdown_max", 100))
    n_tr    = metrics.get("nombre_trades", 0)
    wr      = metrics.get("taux_reussite_pct", 0)

    return (
        0.30 * sharpe
        + 0.25 * (perf / 10)
        + 0.20 * (wr / 100)
        - 0.15 * (dd / 20)
        + 0.10 * min(n_tr / 50, 1.0)
    )


def _build_strategies(ticker: str) -> list[tuple[str, object]]:
    candidates = [
        ("SMA", MovingAverageStrategy()),
        ("RSI", RSIStrategy()),
        ("MACD", MACDStrategy()),
    ]
    try:
        candidates.append(("ML", MLStrategy(ticker)))
    except FileNotFoundError:
        logger.warning(f"[StrategySelector] Modèle ML absent pour {ticker} — ignoré.")
    return candidates


def select_best_strategy(ticker: str, df) -> tuple[str, object, list[dict]]:
    """Backteste toutes les stratégies et retourne la meilleure.

    Returns:
        (strategy_name, strategy_instance, scores_list)
    """
    strategies = _build_strategies(ticker)
    results: list[dict] = []

    for name, strat in strategies:
        try:
            bt = Backtester(strat, initial_capital=INITIAL_CAPITAL)
            ec = bt.run(ticker, df)
            m = compute_metrics(ec, INITIAL_CAPITAL)
            s = _score(m)
            results.append({
                "strategy":      name,
                "sharpe":        m.get("sharpe_ratio", 0),
                "perf_pct":      m.get("performance_totale", 0),
                "drawdown_pct":  m.get("drawdown_max", 0),
                "win_rate_pct":  m.get("taux_reussite_pct", 0),
                "n_trades":      m.get("nombre_trades", 0),
                "score":         s,
            })
            logger.info(f"[StrategySelector] {ticker}/{name} score={s:.3f}")
        except Exception as exc:
            logger.warning(f"[StrategySelector] {ticker}/{name} erreur : {exc}")

    if not results:
        raise RuntimeError(f"Aucune stratégie disponible pour {ticker}")

    results.sort(key=lambda r: r["score"], reverse=True)
    best = results[0]
    best_name = best["strategy"]

    # Retrouve l'instance de la stratégie gagnante
    best_instance = next(s for n, s in strategies if n == best_name)

    logger.info(
        f"[StrategySelector] {ticker} → meilleure stratégie : "
        f"{best_name} (score={best['score']:.3f})"
    )
    return best_name, best_instance, results
