"""
Page Décisions — Historique complet des décisions de l'agent.
"""
from __future__ import annotations
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path: sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from agent import memory as mem

_BG     = "#080c14"
_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"


_TZ_OFFSET = pd.Timedelta(hours=2)  # UTC → heure locale (France UTC+2)

def render(ticker: str, **kwargs):
    st.markdown(f'<h2 style="color:{_TEXT};font-weight:700;margin-bottom:4px;">📋 Historique des Décisions</h2>'
                f'<div style="color:{_MUTED};font-size:13px;margin-bottom:16px;">'
                f'Toutes les décisions prises par l\'agent · Ticker : <b>{ticker}</b></div>',
                unsafe_allow_html=True)

    # ── Boutons hors fragment pour qu'ils fonctionnent correctement ──────────
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 4])
    with btn_col1:
        if st.button("🗑 Effacer tout", key="dec_clear", type="secondary", use_container_width=True):
            mem.clear_decisions(ticker)
            st.toast("Historique effacé.", icon="🗑")
            st.rerun()
    with btn_col2:
        if st.button("⟳ Rafraîchir", key="dec_refresh", use_container_width=True):
            st.rerun()

    @st.fragment(run_every=10)
    def _decisions_content():
        try:
            mem.init_db()
            decisions = mem.get_recent_decisions(ticker, limit=500)
        except Exception as e:
            st.error(f"Impossible de lire la mémoire : {e}")
            return

        if not decisions:
            st.info("Aucune décision enregistrée. Démarrez l'agent depuis la page **Contrôles**.")
            return

        df = pd.DataFrame(decisions)
        df["ts"] = pd.to_datetime(df["ts"], format="mixed", utc=True).dt.tz_localize(None) + _TZ_OFFSET

        # ── Filtres ───────────────────────────────────────────────────────────
        f1, f2, f3 = st.columns(3)
        with f1:
            actions = ["Toutes"] + sorted(df["action"].unique().tolist())
            sel_action = st.selectbox("Action", actions, key="dec_action")
        with f2:
            strategies = ["Toutes"] + sorted(df["strategy"].unique().tolist())
            sel_strat = st.selectbox("Stratégie", strategies, key="dec_strat")
        with f3:
            min_conf = st.slider("Confiance minimale", 0.0, 1.0, 0.0, 0.05, format="%.0f%%", key="dec_conf")

        filtered = df.copy()
        if sel_action != "Toutes":
            filtered = filtered[filtered["action"] == sel_action]
        if sel_strat != "Toutes":
            filtered = filtered[filtered["strategy"] == sel_strat]
        filtered = filtered[filtered["confidence"] >= min_conf]

        st.caption(f"{len(filtered)} décisions affichées sur {len(df)} — rafraîchissement auto toutes les 10s")

        # ── Graphique timeline ─────────────────────────────────────────────────
        color_map = {"BUY": _GREEN, "SELL": _RED, "HOLD": _MUTED}
        fig = go.Figure()
        for action, group in filtered.groupby("action"):
            fig.add_trace(go.Scatter(
                x=group["ts"], y=group["confidence"],
                mode="markers", name=action,
                marker=dict(color=color_map.get(action, _MUTED), size=8, opacity=0.8),
                hovertemplate=(
                    "<b>%{x|%d %b %Y %H:%M}</b><br>"
                    f"Action : {action}<br>"
                    "Confiance : %{y:.0%}<extra></extra>"
                ),
            ))
        fig.add_hline(y=0.60, line_color=_ORANGE, line_dash="dot",
                      annotation_text="  Seuil 60%", annotation_font_color=_ORANGE,
                      annotation_font_size=10)
        fig.update_layout(
            paper_bgcolor=_BG, plot_bgcolor=_BG, font=dict(color=_TEXT),
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis=dict(gridcolor=_GRID, title=""),
            yaxis=dict(gridcolor=_GRID, tickformat=".0%", title="Confiance", range=[0, 1.05]),
            legend=dict(bgcolor="rgba(0,0,0,0)"), height=280,
            title=dict(text="Confiance par décision dans le temps", font=dict(color=_TEXT, size=13), x=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Tableau ───────────────────────────────────────────────────────────
        display = filtered.copy()
        # Extrait le grade [A/B/C/D] de la colonne Raison
        display["grade"] = display["reason"].str.extract(r'^\[([ABCD])\]').fillna("—")
        display["reason"] = display["reason"].str.replace(r'^\[[ABCD]\]\s*', '', regex=True)
        display["ts"] = display["ts"].dt.strftime("%Y-%m-%d %H:%M")
        display["confidence"] = display["confidence"].map(lambda x: f"{x:.0%}")
        display["ml_prob"] = display["ml_prob"].map(lambda x: f"{x:.1%}" if pd.notna(x) else "—")
        display["price"] = display["price"].map(lambda x: f"${x:,.2f}" if pd.notna(x) else "—")
        display = display.rename(columns={
            "ts": "Date/Heure", "action": "Action", "grade": "Grade",
            "confidence": "Confiance", "strategy": "Stratégie",
            "price": "Prix", "ml_prob": "Prob. ML", "reason": "Raison",
        })
        cols = ["Date/Heure", "Action", "Grade", "Confiance", "Stratégie", "Prix", "Prob. ML", "Raison"]
        display = display[[c for c in cols if c in display.columns]]

        _GRADE_COLORS = {"A": "#10b981", "B": "#3b82f6", "C": "#ff9800", "D": "#64748b"}

        def _style_action(val):
            c = _GREEN if val == "BUY" else _RED if val == "SELL" else _MUTED
            return f"color:{c};font-weight:600"

        def _style_grade(val):
            c = _GRADE_COLORS.get(val, _MUTED)
            return f"color:{c};font-weight:700"

        styled = (display.style
                  .map(_style_action, subset=["Action"])
                  .map(_style_grade, subset=["Grade"])
                  .set_properties(**{"font-size": "12px"}))
        st.dataframe(styled, use_container_width=True, height=420, hide_index=True)

        csv = filtered.to_csv(index=False).encode("utf-8")
        st.download_button("⬇ Exporter CSV", csv, "decisions.csv", "text/csv")

    _decisions_content()

