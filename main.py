"""
Point d'entrée principal — trading_ai_agent.

Lance en séquence :
  1. Téléchargement des données de marché.
  2. Entraînement du modèle ML.
  3. Backtest stratégie SMA Crossover.
  4. Backtest stratégie ML (si modèle disponible).
  5. Génération des rapports HTML dans dashboard/.

PAPER TRADING UNIQUEMENT — Aucun ordre réel n'est envoyé.
Ce projet est pédagogique et ne constitue pas un conseil financier.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garantit que les imports fonctionnent quel que soit le répertoire de lancement
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from loguru import logger

from config.settings import DEFAULT_TICKERS, INITIAL_CAPITAL
from data.market_data import load_multiple
from ml.train_model import train as train_model
from backtesting.backtester import Backtester
from backtesting.performance import compute_metrics, print_metrics
from strategies.moving_average_strategy import MovingAverageStrategy
from strategies.ml_strategy import MLStrategy
from dashboard.report import generate_html_report, export_equity_csv
from logs.trade_logger import setup_logger


def main() -> None:
    setup_logger()

    logger.info("=" * 55)
    logger.info("  trading_ai_agent — Paper Trading uniquement")
    logger.info("=" * 55)

    # ── 1. Téléchargement des données ────────────────────────
    logger.info("\n[1/4] Téléchargement des données de marché...")
    all_data = load_multiple(DEFAULT_TICKERS)
    if not all_data:
        logger.error("Aucune donnée téléchargée. Vérifiez votre connexion internet.")
        sys.exit(1)

    # Utilise le premier ticker disponible
    ticker = next(iter(all_data))
    df = all_data[ticker]
    logger.info(f"Ticker principal : {ticker} ({len(df)} barres OHLCV)")

    # ── 2. Entraînement du modèle ML ─────────────────────────
    logger.info("\n[2/4] Entraînement du modèle ML (RandomForest)...")
    ml_trained = False
    try:
        train_model(df, ticker)
        ml_trained = True
    except Exception as exc:
        logger.error(f"Échec de l'entraînement ML : {exc}")

    # ── 3. Backtest — Stratégie SMA ──────────────────────────
    logger.info("\n[3/4] Backtest — Stratégie SMA Crossover (20/50j)...")
    sma_strategy = MovingAverageStrategy()
    sma_bt = Backtester(sma_strategy, initial_capital=INITIAL_CAPITAL)
    sma_equity = sma_bt.run(ticker, df)
    sma_metrics = compute_metrics(sma_equity, INITIAL_CAPITAL)
    print_metrics(sma_metrics, strategy_name=sma_strategy.name)

    sma_report = generate_html_report(
        sma_equity, sma_metrics, sma_strategy.name, ticker,
        filename=f"report_{ticker}_sma.html",
    )
    export_equity_csv(sma_equity, filename=f"equity_{ticker}_sma.csv")
    logger.info(f"Rapport SMA → {sma_report}")

    # ── 4. Backtest — Stratégie ML ───────────────────────────
    if ml_trained:
        logger.info("\n[4/4] Backtest — Stratégie ML RandomForest...")
        try:
            ml_strategy = MLStrategy(ticker=ticker)
            ml_bt = Backtester(ml_strategy, initial_capital=INITIAL_CAPITAL)
            ml_equity = ml_bt.run(ticker, df)
            ml_metrics = compute_metrics(ml_equity, INITIAL_CAPITAL)
            print_metrics(ml_metrics, strategy_name=ml_strategy.name)

            ml_report = generate_html_report(
                ml_equity, ml_metrics, ml_strategy.name, ticker,
                filename=f"report_{ticker}_ml.html",
            )
            export_equity_csv(ml_equity, filename=f"equity_{ticker}_ml.csv")
            logger.info(f"Rapport ML → {ml_report}")
        except Exception as exc:
            logger.warning(f"Backtest ML ignoré : {exc}")
    else:
        logger.info("\n[4/4] Backtest ML ignoré (modèle non disponible).")

    logger.info("\n✓ Terminé. Consultez le dossier dashboard/ pour les rapports HTML.")


if __name__ == "__main__":
    main()
