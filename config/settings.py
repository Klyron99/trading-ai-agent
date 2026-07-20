"""
Centralise tous les paramètres de configuration de l'application.
Les valeurs sont lues depuis les variables d'environnement (.env).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Charge le fichier .env situé à la racine du projet
_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")


# ── Chemins ──────────────────────────────────────────────────────────────────

ROOT_DIR: Path = _ROOT
DATA_CACHE_DIR: Path = ROOT_DIR / "data" / "data_cache"
MODEL_STORE_DIR: Path = ROOT_DIR / "ml" / "model_store"
LOGS_DIR: Path = ROOT_DIR / "logs"
DASHBOARD_DIR: Path = ROOT_DIR / "dashboard"

for _d in (DATA_CACHE_DIR, MODEL_STORE_DIR, LOGS_DIR, DASHBOARD_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ── Général ───────────────────────────────────────────────────────────────────

ENV: str = os.getenv("ENV", "development")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


# ── Capital & tickers ────────────────────────────────────────────────────────

INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL", "10000.0"))
DEFAULT_TICKERS: list[str] = os.getenv("DEFAULT_TICKERS", "BTC-USD,AAPL,MSFT,SPY,QQQ").split(",")
DATA_START_DATE: str = os.getenv("DATA_START_DATE", "2020-01-01")

# Date de fin dynamique : aujourd'hui par défaut (données les plus récentes)
import datetime as _dt
DATA_END_DATE: str = os.getenv(
    "DATA_END_DATE",
    _dt.date.today().strftime("%Y-%m-%d"),
)


# ── Stratégie moyennes mobiles ───────────────────────────────────────────────

MA_SHORT: int = 20
MA_LONG: int = 50


# ── Gestion du risque ────────────────────────────────────────────────────────

RISK_PER_TRADE: float = 0.02       # 2 % du capital max par trade
MAX_POSITION_SIZE: float = 0.20    # 20 % du portefeuille max par position
STOP_LOSS_PCT: float = 0.05        # Stop loss à 5 %


# ── Machine Learning ─────────────────────────────────────────────────────────

ML_TEST_SIZE: float = 0.20
ML_N_ESTIMATORS: int = 100
ML_RANDOM_STATE: int = 42


# ── Alpaca Paper Trading ──────────────────────────────────────────────────────

ALPACA_API_KEY: str | None = os.getenv("ALPACA_API_KEY") or None
ALPACA_SECRET_KEY: str | None = os.getenv("ALPACA_SECRET_KEY") or None
ALPACA_BASE_URL: str = os.getenv(
    "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
)

# URL canonique du paper trading Alpaca — ne jamais modifier
ALPACA_PAPER_URL: str = "https://paper-api.alpaca.markets"

# Garde-fou : si LIVE_TRADING=true dans .env, le bot refusera de fonctionner
LIVE_TRADING: bool = os.getenv("LIVE_TRADING", "false").strip().lower() == "true"


# ── Bot temps réel ───────────────────────────────────────────────────────────

# ETF utilisé pour les tests
LIVE_TICKER: str = os.getenv("LIVE_TICKER", "BTC-USD")

# Vérification toutes les 60 secondes (cohérent avec modèle horaire)
LIVE_INTERVAL_SEC: int = int(os.getenv("LIVE_INTERVAL_SEC", "60"))

# Moyennes mobiles courtes pour générer rapidement des signaux
LIVE_MA_SHORT: int = int(os.getenv("LIVE_MA_SHORT", "25"))
LIVE_MA_LONG: int = int(os.getenv("LIVE_MA_LONG", "50"))


# ── Agent adaptatif ───────────────────────────────────────────────────────────

# Rééentraîne le modèle toutes les N heures
AGENT_RETRAIN_EVERY_HOURS: int = int(os.getenv("AGENT_RETRAIN_EVERY_HOURS", "1"))

# Confidence minimale pour trader (en dessous → HOLD)
AGENT_MIN_CONFIDENCE: float = float(os.getenv("AGENT_MIN_CONFIDENCE", "0.65"))

# Tickers autorisés pour l'agent (défaut = DEFAULT_TICKERS)
AGENT_ALLOWED_TICKERS: list[str] = os.getenv(
    "AGENT_ALLOWED_TICKERS", ",".join(DEFAULT_TICKERS)
).split(",")

# Drawdown maximal avant d'arrêter l'agent (ex: 0.15 = 15 %)
AGENT_MAX_DRAWDOWN: float = float(os.getenv("AGENT_MAX_DRAWDOWN", "0.15"))

# Mode de l'agent : "paper" uniquement (toute autre valeur est rejetée au démarrage)
AGENT_MODE: str = os.getenv("AGENT_MODE", "paper").strip().lower()

# Répertoire de mémoire SQLite de l'agent
AGENT_MEMORY_DIR: Path = ROOT_DIR / "agent" / "memory_store"
AGENT_MEMORY_DIR.mkdir(parents=True, exist_ok=True)