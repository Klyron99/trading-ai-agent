"""
Page Paramètres — Configuration du système et statut des modèles.
"""
from __future__ import annotations
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path: sys.path.insert(0, str(_ROOT))

from pathlib import Path
import streamlit as st

_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"


def _section(title):
    st.markdown(f"""
    <div style="color:{_MUTED};font-size:10px;font-weight:600;
                text-transform:uppercase;letter-spacing:1.5px;
                margin:28px 0 12px;border-bottom:1px solid {_GRID};
                padding-bottom:8px;">{title}</div>
    """, unsafe_allow_html=True)


def _param_row(key, value, ok=None):
    if ok is None:
        color = _TEXT
        icon = ""
    elif ok:
        color = _GREEN
        icon = "✓ "
    else:
        color = _RED
        icon = "✗ "
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;align-items:center;
                padding:8px 0;border-bottom:1px solid {_GRID};">
        <span style="color:{_MUTED};font-size:12px;">{key}</span>
        <span style="color:{color};font-size:12px;font-weight:600;">{icon}{value}</span>
    </div>
    """, unsafe_allow_html=True)


def render(ticker: str, **kwargs):
    import os, datetime
    from pathlib import Path as _P
    _root = _P(__file__).resolve().parents[2]

    AGENT_ALLOWED_TICKERS    = os.getenv("AGENT_ALLOWED_TICKERS", "AAPL,MSFT,SPY,QQQ").split(",")
    AGENT_MAX_DRAWDOWN       = float(os.getenv("AGENT_MAX_DRAWDOWN", "0.15"))
    AGENT_MIN_CONFIDENCE     = float(os.getenv("AGENT_MIN_CONFIDENCE", "0.60"))
    AGENT_MODE               = os.getenv("AGENT_MODE", "paper")
    AGENT_RETRAIN_EVERY_HOURS= int(os.getenv("AGENT_RETRAIN_EVERY_HOURS", "24"))
    INITIAL_CAPITAL          = float(os.getenv("INITIAL_CAPITAL", "10000"))
    LIVE_TRADING             = os.getenv("LIVE_TRADING", "false").lower() == "true"
    MODEL_STORE_DIR          = _root / "ml" / "model_store"
    LOGS_DIR                 = _root / "logs"
    ALPACA_API_KEY           = os.getenv("ALPACA_API_KEY") or None
    DATA_START_DATE          = os.getenv("DATA_START_DATE", "2020-01-01")
    DATA_END_DATE            = os.getenv("DATA_END_DATE", datetime.date.today().strftime("%Y-%m-%d"))
    st.markdown(f'<h2 style="color:{_TEXT};font-weight:700;margin-bottom:4px;">⚙️ Paramètres</h2>'
                f'<div style="color:{_MUTED};font-size:13px;margin-bottom:24px;">'
                f'Configuration du système et statut</div>',
                unsafe_allow_html=True)

    # ── Garde-fous sécurité ───────────────────────────────────────────────────
    _section("🔒 Garde-fous de sécurité")

    _param_row("AGENT_MODE",    AGENT_MODE,         ok=(AGENT_MODE == "paper"))
    _param_row("LIVE_TRADING",  str(LIVE_TRADING),  ok=(not LIVE_TRADING))
    _param_row("URL Alpaca",    "https://paper-api.alpaca.markets", ok=True)

    if LIVE_TRADING:
        st.error("⚠️ LIVE_TRADING=True détecté — l'agent refusera de démarrer.")

    # ── Config agent ──────────────────────────────────────────────────────────
    _section("🤖 Configuration de l'agent")

    _param_row("Confiance minimale",         f"{AGENT_MIN_CONFIDENCE:.0%}")
    _param_row("Drawdown max avant arrêt",   f"{AGENT_MAX_DRAWDOWN:.0%}")
    _param_row("Réentraînement toutes les",  f"{AGENT_RETRAIN_EVERY_HOURS}h")
    _param_row("Capital initial (simulation)", f"${INITIAL_CAPITAL:,.0f}")
    _param_row("Tickers autorisés",          ", ".join(AGENT_ALLOWED_TICKERS))
    _param_row("Données de",                 f"{DATA_START_DATE} → {DATA_END_DATE}")

    # ── Alpaca ────────────────────────────────────────────────────────────────
    _section("📡 Connexion Alpaca")

    if ALPACA_API_KEY:
        _param_row("Clé API",   "Configurée ✓", ok=True)
        _param_row("Mode",      "Alpaca Paper Trading", ok=True)
    else:
        _param_row("Clé API",   "Non configurée", ok=False)
        _param_row("Mode",      "Simulation yfinance (aucun compte requis)", ok=True)
        st.markdown(f"""
        <div style="background:{_CARD};border-left:3px solid {_ORANGE};
                    border-radius:0 6px 6px 0;padding:12px 16px;
                    color:{_MUTED};font-size:12px;margin-top:8px;">
            Pour utiliser Alpaca Paper Trading, créez un fichier <code>.env</code> à la racine avec :<br>
            <code>ALPACA_API_KEY=votre_cle</code><br>
            <code>ALPACA_SECRET_KEY=votre_secret</code>
        </div>
        """, unsafe_allow_html=True)

    # ── Modèles entraînés ─────────────────────────────────────────────────────
    _section("🧠 Modèles ML entraînés")

    models = list(MODEL_STORE_DIR.glob("*_rf_model.joblib"))
    if models:
        for m in sorted(models):
            size_kb = m.stat().st_size / 1024
            import datetime
            mtime = datetime.datetime.fromtimestamp(m.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            ticker_name = m.stem.replace("_rf_model", "")
            _param_row(f"{ticker_name}", f"{size_kb:.0f} KB · entraîné le {mtime}", ok=True)
    else:
        st.info("Aucun modèle entraîné. Allez dans **Contrôles → Réentraîner**.")

    # ── Logs ──────────────────────────────────────────────────────────────────
    _section("📄 Logs récents")

    log_files = sorted(LOGS_DIR.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if log_files:
        sel_log = st.selectbox("Fichier de log", [f.name for f in log_files], key="param_log")
        log_path = LOGS_DIR / sel_log
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            last_lines = "\n".join(lines[-100:])
            st.code(last_lines, language=None)
        except Exception as e:
            st.error(str(e))
    else:
        st.info("Aucun fichier de log trouvé.")

    # ── .env guide ────────────────────────────────────────────────────────────
    _section("📝 Fichier .env (configuration)")

    st.markdown(f"""
    <div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;padding:16px 20px;">
    <pre style="color:{_TEXT};font-size:12px;margin:0;line-height:1.8;"># Créez ce fichier à la racine : trading_ai_agent/.env

# Capital de simulation
INITIAL_CAPITAL=10000

# Alpaca Paper Trading (optionnel)
ALPACA_API_KEY=
ALPACA_SECRET_KEY=

# Agent
AGENT_MIN_CONFIDENCE=0.60
AGENT_MAX_DRAWDOWN=0.15
AGENT_RETRAIN_EVERY_HOURS=1
AGENT_ALLOWED_TICKERS=AAPL,MSFT,SPY,QQQ
AGENT_MODE=paper

# Sécurité — NE PAS CHANGER
LIVE_TRADING=false</pre>
    </div>
    """, unsafe_allow_html=True)

