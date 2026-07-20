""" Affichage en temps réel des logs de l'agent et du dashboard.
"""
from __future__ import annotations
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"

_LOGS_DIR = _ROOT / "logs"

# Ordre : les plus importants en premier (= sélection par défaut)
_LOG_FILES = {
    "Agent (erreurs de démarrage)":  "agent_subprocess.log",
    "Dashboard Streamlit":           "streamlit_dashboard.log",
    "Live paper trading":            "live_paper_trading.log",
    "Trading general":               "trading.log",
}

_LEVEL_COLORS = {
    "ERROR":    _RED,
    "CRITICAL": _RED,
    "WARNING":  _ORANGE,
    "SUCCESS":  _GREEN,
    "INFO":     _TEXT,
    "DEBUG":    _MUTED,
    "Traceback": _RED,
    "Exception": _RED,
}


def _colorize(line: str) -> str:
    import html
    safe = html.escape(line)
    for kw, color in _LEVEL_COLORS.items():
        if kw in line:
            return f'<span style="color:{color};">{safe}</span>'
    return f'<span style="color:{_MUTED};">{safe}</span>'


def render(ticker: str = "QQQ", **kwargs):
    st.markdown(
        f'<h2 style="color:{_TEXT};font-weight:700;margin-bottom:4px;">"" Logs</h2>'
        f'<div style="color:{_MUTED};font-size:13px;margin-bottom:24px;"—" agent, dashboard et trading</div>',
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        log_label = st.selectbox("Fichier de log", list(_LOG_FILES.keys()), key="logs_file_sel")
    with col2:
        n_lines = st.selectbox("Dernières lignes", [50, 100, 200, 500], key="logs_nlines")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        auto = st.toggle("Auto-refresh (5s)", value=True, key="logs_auto")

    log_filename = _LOG_FILES[log_label]
    log_path = _LOGS_DIR / log_filename

    # -"?-"? Astuce : si c'est le log Streamlit, on indique comment le générer -"?-"?
    if "streamlit" in log_filename.lower() and not log_path.exists():
        st.markdown(
            f'<div style="background:{_CARD};border-left:3px solid {_ORANGE};'
            f'border-radius:0 6px 6px 0;padding:12px 16px;color:{_TEXT};font-size:13px;">'
            f'Pour capturer les logs du dashboard, relance Streamlit avec cette commande :<br><br>'
            f'<code style="background:#0d1117;padding:6px 10px;border-radius:4px;font-size:12px;">'
            f'python -m streamlit run dashboard/app.py 2>&1 | tee logs/streamlit_dashboard.log'
            f'</code></div>',
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

    @st.fragment(run_every=5 if auto else None)
    def _log_viewer():
        if not log_path.exists():
            st.info(f"Le fichier sera cree au prochain demarrage de l'agent.")
            return

        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            st.error(str(e))
            return

        last = lines[-n_lines:]

        # -"?-"? Métriques rapides -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
        errors   = sum(1 for l in last if "ERROR"   in l or "Traceback" in l or "Exception" in l)
        warnings = sum(1 for l in last if "WARNING" in l)
        buys     = sum(1 for l in last if " BUY"    in l)
        sells    = sum(1 for l in last if " SELL"   in l)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Erreurs",   errors,   delta=None)
        m2.metric("Warnings",  warnings, delta=None)
        m3.metric("BUY vus",   buys,     delta=None)
        m4.metric("SELL vus",  sells,    delta=None)

        # -"?-"? Alerte si erreurs récentes -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
        recent_errors = [l for l in last[-20:] if "ERROR" in l or "Traceback" in l or "Exception" in l]
        if recent_errors:
            st.markdown(
                f'<div style="background:rgba(239,83,80,0.08);border:1px solid {_RED};'
                f'border-radius:6px;padding:10px 14px;margin-bottom:12px;">'
                f'<span style="color:{_RED};font-weight:700;">-s- {len(recent_errors)} erreur(s) récente(s)</span><br>'
                f'<code style="color:{_RED};font-size:11px;">'
                + '<br>'.join(recent_errors[-3:]) +
                f'</code></div>',
                unsafe_allow_html=True,
            )

        # -"?-"? Log colorisé -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
        colored = "<br>".join(_colorize(l) for l in last)
        st.markdown(
            f'<div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;'
            f'padding:14px 16px;font-family:monospace;font-size:11px;line-height:1.7;'
            f'max-height:520px;overflow-y:auto;">'
            f'{colored}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"{log_path} · {len(lines)} lignes totales · mis à jour en temps réel")

    _log_viewer()

    # -"?-"? Téléchargement -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    if log_path.exists():
        st.download_button(
            "Télécharger le log complet",
            data=log_path.read_bytes(),
            file_name=log_path.name,
            mime="text/plain",
            key="logs_dl_btn",
        )
