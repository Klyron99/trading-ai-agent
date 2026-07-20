"""
Bot de paper trading en temps réel — trading_ai_agent.

Fonctionnement :
  1. Connexion à Alpaca Paper Trading (ou mode simulation si pas de clés).
  2. Récupération du prix toutes les LIVE_INTERVAL_SEC secondes.
  3. Calcul des moyennes mobiles courte et longue sur un buffer glissant.
  4. Génération d'un signal achat / vente / neutre.
  5. Validation par le RiskManager (taille de position, stop loss).
  6. Envoi de l'ordre en paper trading uniquement.
  7. Arrêt propre sur Ctrl+C.

PAPER TRADING UNIQUEMENT — Aucun ordre réel n'est envoyé.
Ce script ne constitue pas un conseil financier.

Lancement :
    python live_paper_trading.py
"""

from __future__ import annotations

import signal
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

# Garantit les imports depuis la racine du projet
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from loguru import logger

from config.settings import (
    LIVE_INTERVAL_SEC,
    LIVE_MA_LONG,
    LIVE_MA_SHORT,
    LIVE_TICKER,
    LIVE_TRADING,
    MAX_POSITION_SIZE,
    RISK_PER_TRADE,
    STOP_LOSS_PCT,
)
from execution.alpaca_paper_broker import AlpacaPaperBroker
from logs.trade_logger import setup_logger
from risk.risk_manager import OrderRequest, RiskManager


# ── Constantes ────────────────────────────────────────────────────────────────

_PAPER_BANNER = """
╔══════════════════════════════════════════════════════════╗
║         trading_ai_agent — PAPER TRADING BOT            ║
║                                                          ║
║  ⚠  PAPER TRADING UNIQUEMENT — Aucun ordre réel         ║
║  ⚠  Ce script n'est pas un conseil financier            ║
╚══════════════════════════════════════════════════════════╝
"""


# ── Signal handler pour arrêt propre ─────────────────────────────────────────

_running: bool = True


def _handle_sigint(sig, frame) -> None:  # noqa: ANN001
    global _running
    logger.info("\n[Bot] Signal d'arrêt reçu (Ctrl+C). Arrêt en cours...")
    _running = False


signal.signal(signal.SIGINT, _handle_sigint)
signal.signal(signal.SIGTERM, _handle_sigint)


# ── Calcul des moyennes mobiles ───────────────────────────────────────────────

def compute_signal(prices: deque[float], short: int, long_: int) -> int:
    """Calcule le signal de trading à partir d'un buffer de prix.

    Args:
        prices: Buffer glissant de prix de clôture.
        short: Nombre de barres pour la MA courte.
        long_: Nombre de barres pour la MA longue.

    Returns:
        1 (achat), -1 (vente), 0 (neutre / pas assez de données).
    """
    if len(prices) < long_:
        return 0  # Buffer insuffisant, on attend

    prices_list = list(prices)
    ma_short = sum(prices_list[-short:]) / short
    ma_long = sum(prices_list[-long_:]) / long_

    if ma_short > ma_long:
        return 1
    if ma_short < ma_long:
        return -1
    return 0


# ── Boucle principale ────────────────────────────────────────────────────────

def run_bot(
    ticker: str = LIVE_TICKER,
    interval_sec: int = LIVE_INTERVAL_SEC,
    ma_short: int = LIVE_MA_SHORT,
    ma_long: int = LIVE_MA_LONG,
) -> None:
    """Lance la boucle de paper trading en temps réel.

    Args:
        ticker: Symbole boursier à surveiller.
        interval_sec: Secondes entre chaque cycle.
        ma_short: Fenêtre de la moyenne mobile courte.
        ma_long: Fenêtre de la moyenne mobile longue.
    """
    print(_PAPER_BANNER)
    setup_logger(log_file="live_paper_trading.log")

    logger.info(f"[Bot] Démarrage — ticker={ticker} | interval={interval_sec}s "
                f"| MA({ma_short}/{ma_long})")

    # Vérification de sécurité préliminaire
    if LIVE_TRADING:
        logger.critical(
            "[Bot] ARRÊT D'URGENCE : LIVE_TRADING=true détecté. "
            "Ce bot est réservé au PAPER TRADING. "
            "Remettez LIVE_TRADING=false dans .env."
        )
        sys.exit(1)

    # Initialisation du broker (déclenche les gardes-fous URL + LIVE_TRADING)
    try:
        broker = AlpacaPaperBroker()
    except EnvironmentError as exc:
        logger.critical(f"[Bot] Environnement non sécurisé : {exc}")
        sys.exit(1)

    risk_manager = RiskManager(
        risk_per_trade=RISK_PER_TRADE,
        max_position_size=MAX_POSITION_SIZE,
        stop_loss_pct=STOP_LOSS_PCT,
    )

    # Affiche l'état du compte au démarrage
    broker.log_account_summary()

    # Buffer glissant de prix (taille = ma_long * 2 pour marge)
    price_buffer: deque[float] = deque(maxlen=ma_long * 2)

    cycle = 0
    last_signal = 0  # Mémorisation du dernier signal pour éviter les doublons

    logger.info(f"[Bot] En écoute sur {ticker} — Ctrl+C pour arrêter.")

    while _running:
        cycle += 1
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        try:
            # ── Récupération du prix ─────────────────────────────────────────
            price = broker.get_latest_price(ticker)
            price_buffer.append(price)
            logger.info(
                f"[Bot] Cycle {cycle:04d} | {now} | {ticker} = {price:.2f} $ "
                f"| Buffer : {len(price_buffer)}/{ma_long} barres"
            )

            # ── Calcul du signal ─────────────────────────────────────────────
            signal = compute_signal(price_buffer, ma_short, ma_long)
            signal_label = {1: "▲ ACHAT", -1: "▼ VENTE", 0: "— NEUTRE"}.get(signal, "?")
            logger.info(f"[Bot] Signal : {signal_label}")

            if signal == 0:
                _wait(interval_sec)
                continue

            # ── Récupération du compte ───────────────────────────────────────
            account = broker.get_account()
            portfolio_value = account.portfolio_value
            cash = account.cash

            # ── Traitement signal ACHAT ──────────────────────────────────────
            if signal == 1 and signal != last_signal:
                # Anti-doublon : on ne rachète pas si on a déjà une position
                existing = broker.get_position(ticker)
                if existing:
                    logger.info(
                        f"[Bot] Position déjà ouverte sur {ticker} "
                        f"({existing['qty']} actions @ {existing['avg_price']:.2f} $). "
                        "Achat ignoré."
                    )
                    last_signal = signal
                    _wait(interval_sec)
                    continue

                # Anti-doublon ordre en attente
                if broker.has_open_order(ticker):
                    _wait(interval_sec)
                    continue

                # Calcul de la quantité via le RiskManager
                qty = risk_manager.compute_position_size(price, portfolio_value)
                if qty <= 0:
                    logger.warning(
                        f"[Bot] Quantité calculée = 0 pour {ticker} "
                        f"(capital={portfolio_value:.2f} $, prix={price:.2f} $). "
                        "Ordre ignoré."
                    )
                    _wait(interval_sec)
                    continue

                # Validation risque
                order_req = OrderRequest(
                    ticker=ticker,
                    side="buy",
                    price=price,
                    quantity=qty,
                    portfolio_value=portfolio_value,
                    cash=cash,
                )
                valid, reason = risk_manager.validate(order_req)
                if not valid:
                    logger.warning(f"[Bot] Achat bloqué par le RiskManager : {reason}")
                    _wait(interval_sec)
                    continue

                # Envoi de l'ordre paper
                result = broker.submit_market_order(ticker, "buy", qty)
                logger.success(
                    f"[Bot] ACHAT PAPER exécuté | {ticker} x{qty} | "
                    f"Ordre ID : {result.order_id} | Simulé : {result.simulated}"
                )
                last_signal = signal

            # ── Traitement signal VENTE ──────────────────────────────────────
            elif signal == -1 and signal != last_signal:
                position = broker.get_position(ticker)
                if not position:
                    logger.info(f"[Bot] Pas de position ouverte sur {ticker}. Vente ignorée.")
                    last_signal = signal
                    _wait(interval_sec)
                    continue

                if broker.has_open_order(ticker):
                    _wait(interval_sec)
                    continue

                # Vérification stop loss
                avg_price = position["avg_price"]
                qty = position["qty"]
                if risk_manager.check_stop_loss(avg_price, price):
                    logger.warning(
                        f"[Bot] Stop loss déclenché sur {ticker} | "
                        f"Entrée : {avg_price:.2f} $ | Actuel : {price:.2f} $"
                    )

                result = broker.submit_market_order(ticker, "sell", qty)
                pnl = (price - avg_price) * qty
                logger.success(
                    f"[Bot] VENTE PAPER exécutée | {ticker} x{qty} | "
                    f"PnL estimé : {pnl:+.2f} $ | Ordre ID : {result.order_id}"
                )
                last_signal = signal

            else:
                logger.debug(f"[Bot] Signal identique au précédent ({signal_label}), ignoré.")

            # Affiche le résumé du compte à chaque cycle avec signal
            broker.log_account_summary()

        except RuntimeError as exc:
            # Erreur de prix (API down, marché fermé…) — on continue
            logger.error(f"[Bot] Erreur récupération prix : {exc}")
            logger.info("[Bot] Nouvelle tentative au prochain cycle.")

        except Exception as exc:
            logger.exception(f"[Bot] Erreur inattendue cycle {cycle} : {exc}")

        _wait(interval_sec)

    # ── Arrêt propre ────────────────────────────────────────────────────────
    logger.info("[Bot] Boucle terminée proprement.")
    broker.log_account_summary()
    logger.info(
        f"[Bot] Session terminée — {cycle} cycles effectués sur {ticker}. "
        "Logs disponibles dans logs/live_paper_trading.log"
    )


def _wait(seconds: int) -> None:
    """Attend en découpant le sleep pour rester réactif à Ctrl+C."""
    global _running
    for _ in range(seconds):
        if not _running:
            break
        time.sleep(1)


# ── Point d'entrée ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_bot()
