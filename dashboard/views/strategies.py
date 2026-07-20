"""
Page Stratégies — Comparaison et performance des stratégies de l'agent.
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

_STRAT_COLORS = {"SMA": _BLUE, "RSI": _GREEN, "MACD": _ORANGE, "ML": "#9c27b0"}


def _card(label, value, color=None, sub=None):
    color = color or _TEXT
    sub_html = f'<div style="color:{_MUTED};font-size:11px;margin-top:4px;">{sub}</div>' if sub else ""
    st.markdown(f"""
    <div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;padding:16px 20px;">
        <div style="color:{_MUTED};font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1px;">{label}</div>
        <div style="color:{color};font-size:22px;font-weight:700;margin-top:6px;">{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def render(ticker: str, **kwargs):
    st.markdown(f'<h2 style="color:{_TEXT};font-weight:700;margin-bottom:4px;">🏆 Stratégies</h2>'
                f'<div style="color:{_MUTED};font-size:13px;margin-bottom:24px;">'
                f'Comparaison et sélection automatique · Ticker : <b>{ticker}</b></div>',
                unsafe_allow_html=True)

    try:
        mem.init_db()
        comparison = mem.get_strategy_comparison(ticker)
        best = mem.get_best_strategy(ticker)
    except Exception as e:
        st.error(f"Impossible de lire la mémoire : {e}")
        return

    if not comparison:
        st.info(
            "Aucune évaluation disponible. Lancez un réentraînement depuis la page **Contrôles** "
            "pour comparer les stratégies."
        )
        _show_strategies_explanation()
        return

    df = pd.DataFrame(comparison)

    # ── Meilleure stratégie ───────────────────────────────────────────────────
    if best:
        best_row = next((r for r in comparison if r["strategy"] == best), comparison[0])
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            _card("Stratégie sélectionnée", best,
                  color=_STRAT_COLORS.get(best, _BLUE), sub="Meilleur score composite")
        with c2:
            _card("Score composite", f"{best_row.get('score', 0):.3f}", color=_GREEN)
        with c3:
            _card("Sharpe ratio", f"{best_row.get('sharpe', 0):.3f}", color=_BLUE)
        with c4:
            _card("Win Rate", f"{best_row.get('win_rate_pct', 0):.1f}%",
                  color=_GREEN if best_row.get('win_rate_pct', 0) > 50 else _RED)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Graphique comparaison scores ──────────────────────────────────────────
    strats = [r["strategy"] for r in comparison]
    scores = [r.get("score", 0) for r in comparison]
    colors = [_STRAT_COLORS.get(s, _BLUE) for s in strats]

    fig = go.Figure(go.Bar(
        x=strats, y=scores,
        marker_color=colors,
        text=[f"{s:.3f}" for s in scores], textposition="outside",
        hovertemplate="<b>%{x}</b><br>Score : %{y:.3f}<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=_BG, plot_bgcolor=_BG,
        font=dict(color=_TEXT),
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(gridcolor=_GRID),
        yaxis=dict(gridcolor=_GRID, title="Score composite"),
        title=dict(text="Score composite par stratégie", font=dict(color=_TEXT, size=13), x=0),
        showlegend=False, height=280,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Radar chart ───────────────────────────────────────────────────────────
    categories = ["Sharpe", "Perf %", "Win Rate %", "Drawdown (inv.)", "Score"]
    fig2 = go.Figure()
    for r in comparison:
        dd_inv = max(0, 20 - abs(r.get("drawdown_pct", 0))) / 20  # inversé et normalisé
        vals = [
            min(max(r.get("sharpe", 0), 0), 3) / 3,
            min(max(r.get("perf_pct", 0), -20), 30) / 30,
            r.get("win_rate_pct", 0) / 100,
            dd_inv,
            min(max(r.get("score", 0), -1), 1),
        ]
        fig2.add_trace(go.Scatterpolar(
            r=vals + [vals[0]],
            theta=categories + [categories[0]],
            name=r["strategy"],
            line=dict(color=_STRAT_COLORS.get(r["strategy"], _BLUE), width=2),
            fill="toself",
            fillcolor=f"rgba({_hex_rgb(_STRAT_COLORS.get(r['strategy'], _BLUE))},0.1)",
        ))
    fig2.update_layout(
        polar=dict(
            bgcolor=_CARD,
            radialaxis=dict(visible=True, range=[0, 1], tickformat=".0%", gridcolor=_GRID, linecolor=_GRID),
            angularaxis=dict(gridcolor=_GRID, linecolor=_GRID),
        ),
        paper_bgcolor=_BG, font=dict(color=_TEXT),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=40, r=40, t=50, b=20),
        title=dict(text="Profil des stratégies", font=dict(color=_TEXT, size=13), x=0),
        height=350,
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── Tableau détaillé ──────────────────────────────────────────────────────
    st.markdown(f'<div style="color:{_MUTED};font-size:10px;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:1px;margin:16px 0 8px;">Détail des métriques</div>',
                unsafe_allow_html=True)

    df_display = df.rename(columns={
        "strategy": "Stratégie", "sharpe": "Sharpe", "perf_pct": "Perf (%)",
        "drawdown_pct": "Drawdown (%)", "win_rate_pct": "Win Rate (%)",
        "n_trades": "Trades", "score": "Score", "ts": "Évalué le",
    })

    def _highlight(row):
        if row["Stratégie"] == best:
            return [f"background-color:rgba(41,98,255,0.12);font-weight:600"] * len(row)
        return [""] * len(row)

    styled = (
        df_display.style
        .apply(_highlight, axis=1)
        .format({"Sharpe": "{:.3f}", "Perf (%)": "{:+.2f}%",
                 "Drawdown (%)": "{:.2f}%", "Win Rate (%)": "{:.1f}%", "Score": "{:.3f}"})
        .set_properties(**{"font-size": "12px"})
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    _show_strategies_explanation()


def _show_strategies_explanation():
    _CARD_ = "#0f1724"
    _GRID_ = "#1a2235"
    _TEXT_ = "#e2e8f0"
    _MUTED_= "#64748b"
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"""
    <div style="background:{_CARD_};border:1px solid {_GRID_};border-radius:8px;padding:16px 20px;">
        <div style="color:{_TEXT_};font-size:13px;font-weight:600;margin-bottom:12px;">
            📖 Les 4 stratégies de l'agent
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:12px;color:{_TEXT_};">
            <tr style="border-bottom:1px solid {_GRID_};">
                <td style="padding:8px 12px;color:#2962ff;font-weight:700;">SMA</td>
                <td style="padding:8px 12px;">Croisement moyennes mobiles 20/50j — suit la tendance</td>
            </tr>
            <tr style="border-bottom:1px solid {_GRID_};">
                <td style="padding:8px 12px;color:#26a69a;font-weight:700;">RSI</td>
                <td style="padding:8px 12px;">RSI 14j — achète survente (&lt;30), vend surachat (&gt;70)</td>
            </tr>
            <tr style="border-bottom:1px solid {_GRID_};">
                <td style="padding:8px 12px;color:#ff9800;font-weight:700;">MACD</td>
                <td style="padding:8px 12px;">Croisement MACD/Signal — capture changements de momentum</td>
            </tr>
            <tr>
                <td style="padding:8px 12px;color:#9c27b0;font-weight:700;">ML</td>
                <td style="padding:8px 12px;">RandomForest — apprend sur données historiques, prédit la direction</td>
            </tr>
        </table>
        <div style="color:{_MUTED_};font-size:11px;margin-top:12px;">
            Score composite = 30% Sharpe + 25% Perf + 20% Win Rate − 15% Drawdown + 10% Activité
        </div>
    </div>
    """, unsafe_allow_html=True)


def _hex_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"

