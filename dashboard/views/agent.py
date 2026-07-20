"""—" Tableau de bord de l'agent adaptatif.
Affiche : stratégie active, modèle, confiance, dernier réentraînement,
comparaison des stratégies et historique des décisions.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.metrics import divider, kpi_card, section_title

# Couleurs partagées
_BG     = "#080c14"
_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"


@st.cache_data(ttl=30)
def _load_agent_data(ticker: str):
    """Charge les données de l'agent depuis la mémoire SQLite."""
    try:
        from agent import memory as mem
        mem.init_db()

        best_strat  = mem.get_best_strategy(ticker)
        comparison  = mem.get_strategy_comparison(ticker)
        decisions   = mem.get_recent_decisions(ticker, limit=100)
        last_model  = mem.get_last_model(ticker)
        return {
            "best_strategy": best_strat,
            "comparison":    comparison,
            "decisions":     decisions,
            "last_model":    last_model,
            "ok": True,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _strategy_color(name: str) -> str:
    colors = {"SMA": _BLUE, "RSI": _GREEN, "MACD": _ORANGE, "ML": "#9c27b0"}
    return colors.get(name, _TEXT)


def _action_color(action: str) -> str:
    return _GREEN if action == "BUY" else _RED if action == "SELL" else _MUTED


def render(ticker: str, **kwargs) -> None:
    st.markdown(
        f'<h2 style="color:{_TEXT};font-weight:700;margin-bottom:4px;">-Y-- Agent Adaptatif</h2>'
        f'<div style="color:{_MUTED};font-size:13px;margin-bottom:24px;">'
        f'Surveillance en temps réel · Paper trading uniquement · Ticker : <b>{ticker}</b></div>',
        unsafe_allow_html=True,
    )

    data = _load_agent_data(ticker)

    if not data["ok"]:
        st.warning(
            f"La mémoire de l'agent est vide ou inaccessible. "
            f"Lancez d'abord `python retrain_agent.py` pour initialiser.\n\n"
            f"Détail : {data.get('error', '')}"
        )
        _show_quickstart()
        return

    # -"?-"? KPI row -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    col1, col2, col3, col4 = st.columns(4)

    best_strat = data["best_strategy"] or "—"
    last_model = data["last_model"]
    decisions  = data["decisions"]

    with col1:
        kpi_card(
            "Stratégie active",
            best_strat,
            color=_strategy_color(best_strat),
        )
    with col2:
        model_type = last_model["model_type"] if last_model else "—"
        kpi_card("Modèle ML", model_type)
    with col3:
        if decisions:
            last = decisions[0]
            conf = f"{last['confidence']:.0%}"
            color = _GREEN if last["confidence"] >= 0.65 else _ORANGE if last["confidence"] >= 0.55 else _RED
        else:
            conf, color = "—", _MUTED
        kpi_card("Dernière confiance", conf, color=color)
    with col4:
        if last_model:
            ts = last_model["ts"][:16].replace("T", " ")
        else:
            ts = "—"
        kpi_card("Dernier réentraînement", ts)

    divider()

    # -"?-"? Comparaison stratégies -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Comparaison des Stratégies")

    comparison = data["comparison"]
    if comparison:
        df_cmp = pd.DataFrame(comparison)
        df_cmp = df_cmp.rename(columns={
            "strategy":     "Stratégie",
            "sharpe":       "Sharpe",
            "perf_pct":     "Perf (%)",
            "drawdown_pct": "Drawdown (%)",
            "win_rate_pct": "Win Rate (%)",
            "n_trades":     "Trades",
            "score":        "Score",
            "ts":           "-?valué le",
        })

        # Colorie la meilleure ligne
        def _highlight_best(row):
            if row["Stratégie"] == best_strat:
                return [f"background-color:rgba(41,98,255,0.12);color:{_TEXT}"] * len(row)
            return [""] * len(row)

        styled = (
            df_cmp.style
            .apply(_highlight_best, axis=1)
            .format({
                "Sharpe":       "{:.3f}",
                "Perf (%)":     "{:+.2f}%",
                "Drawdown (%)": "{:.2f}%",
                "Win Rate (%)": "{:.1f}%",
                "Score":        "{:.3f}",
            })
            .set_properties(**{"font-size": "12px"})
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune évaluation disponible. Lancez `python retrain_agent.py`.")

    divider()

    # -"?-"? Historique des décisions -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Historique des Décisions")

    if decisions:
        df_dec = pd.DataFrame(decisions)
        df_dec["ts"] = df_dec["ts"].str[:16].str.replace("T", " ")
        df_dec = df_dec.rename(columns={
            "ts":         "Date/Heure",
            "action":     "Action",
            "confidence": "Confiance",
            "strategy":   "Stratégie",
            "price":      "Prix ($)",
            "ml_prob":    "Prob. ML",
            "reason":     "Raison",
        })
        display_cols = ["Date/Heure", "Action", "Confiance", "Stratégie",
                        "Prix ($)", "Prob. ML", "Raison"]
        df_dec = df_dec[[c for c in display_cols if c in df_dec.columns]]

        def _color_action(val):
            return f"color:{_action_color(val)};font-weight:600"

        fmt = {"Confiance": "{:.0%}"}
        if "Prix ($)" in df_dec.columns:
            fmt["Prix ($)"] = "${:,.2f}"
        if "Prob. ML" in df_dec.columns:
            fmt["Prob. ML"] = lambda v: f"{v:.1%}" if pd.notna(v) else "—"

        styled_dec = (
            df_dec.style
            .applymap(_color_action, subset=["Action"])
            .format(fmt, na_rep="—")
            .set_properties(**{"font-size": "12px"})
        )
        st.dataframe(styled_dec, use_container_width=True, height=400, hide_index=True)

        # Distribution des actions
        col_a, col_b = st.columns(2)
        with col_a:
            counts = df_dec["Action"].value_counts()
            import plotly.graph_objects as go
            colors = [_action_color(a) for a in counts.index]
            fig = go.Figure(go.Bar(
                x=counts.index, y=counts.values,
                marker_color=colors,
                text=counts.values, textposition="outside",
            ))
            fig.update_layout(
                paper_bgcolor=_BG, plot_bgcolor=_BG,
                font=dict(color=_TEXT),
                margin=dict(l=10, r=10, t=30, b=10),
                title=dict(text="Distribution des Actions", font=dict(color=_TEXT, size=13), x=0),
                showlegend=False,
                xaxis=dict(gridcolor=_GRID),
                yaxis=dict(gridcolor=_GRID),
                height=250,
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            conf_series = pd.to_numeric(
                df_dec["Confiance"].astype(str).str.rstrip("%"), errors="coerce"
            ) / 100
            conf_series = conf_series.dropna()
            if not conf_series.empty:
                fig2 = go.Figure(go.Histogram(
                    x=conf_series, nbinsx=20,
                    marker_color=_BLUE, opacity=0.8,
                    hovertemplate="Confiance %{x:.0%}<br>Count : %{y}<extra></extra>",
                ))
                fig2.add_vline(
                    x=0.60, line_color=_GREEN, line_dash="dot",
                    annotation_text="  Seuil 60%",
                    annotation_font_color=_GREEN, annotation_font_size=10,
                )
                fig2.update_layout(
                    paper_bgcolor=_BG, plot_bgcolor=_BG,
                    font=dict(color=_TEXT),
                    margin=dict(l=10, r=10, t=30, b=10),
                    title=dict(text="Distribution Confiance", font=dict(color=_TEXT, size=13), x=0),
                    xaxis=dict(gridcolor=_GRID, tickformat=".0%"),
                    yaxis=dict(gridcolor=_GRID),
                    height=250,
                )
                st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Aucune décision enregistrée. Lancez `python run_agent.py` pour démarrer.")

    divider()
    _show_quickstart()


def _show_quickstart() -> None:
    st.markdown(
        f"""
        <div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;padding:16px 20px;">
            <div style="font-size:13px;font-weight:600;color:{_TEXT};margin-bottom:12px;">
                -s- Commandes rapides
            </div>
            <div style="font-family:monospace;font-size:12px;line-height:2;color:{_MUTED};">
                <span style="color:{_GREEN};"># Réentraîner les modèles</span><br>
                python retrain_agent.py<br><br>
                <span style="color:{_GREEN};"># Lancer l'agent (1 tick / minute)</span><br>
                python run_agent.py --ticker AAPL --interval 60<br><br>
                <span style="color:{_GREEN};"># Lancer l'agent sur QQQ toutes les 30s</span><br>
                python run_agent.py --ticker QQQ --interval 30
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
