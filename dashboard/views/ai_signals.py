"""—" Analyse ML : probabilités, features, RSI, confiance.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.charts import (
    bull_probability_gauge,
    feature_importance_chart,
    rsi_chart,
)
from dashboard.components.metrics import divider, kpi_card, section_title, signal_badge
from dashboard.components.tables import features_table
from dashboard.data_loader import get_ml_analysis, get_ohlcv

_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"
_MUTED  = "#64748b"
_BG     = "#080c14"
_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"


def _confidence_bar(probability: float) -> None:
    """Barre de confiance horizontale stylisée."""
    pct = probability * 100
    color = _GREEN if pct > 55 else _RED if pct < 45 else _ORANGE
    inv_pct = 100 - pct
    st.markdown(
        f"""
        <div style="margin:8px 0 16px;">
            <div style="display:flex;justify-content:space-between;
                        font-size:11px;color:{_MUTED};margin-bottom:4px;">
                <span>BAISSIER</span>
                <span>NEUTRE</span>
                <span>HAUSSIER</span>
            </div>
            <div style="background:{_CARD};border:1px solid {_GRID};
                        border-radius:20px;height:12px;overflow:hidden;">
                <div style="width:{pct:.1f}%;height:100%;
                            background:linear-gradient(90deg,{_RED},{color});
                            border-radius:20px;transition:width 0.3s;"></div>
            </div>
            <div style="text-align:center;font-size:22px;font-weight:700;
                        color:{color};margin-top:8px;">{pct:.1f}%</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _feature_sparklines(features_df: pd.DataFrame) -> None:
    """Mini-graphiques des features sur les 60 dernières barres."""
    tail = features_df.tail(60)
    cols_to_show = [c for c in ["returns_1d", "ma_ratio", "volatility", "rsi_14"] if c in tail.columns]

    if not cols_to_show:
        return

    cols = st.columns(len(cols_to_show))
    labels_map = {
        "returns_1d": "Rendements 1j",
        "returns_5d": "Rendements 5j",
        "ma_ratio":   "Ratio MA20/MA50",
        "volatility": "Volatilité",
        "rsi_14":     "RSI 14",
    }

    for col, feat in zip(cols, cols_to_show):
        with col:
            series = tail[feat].dropna()
            if series.empty:
                continue

            last_val = float(series.iloc[-1])
            prev_val = float(series.iloc[-2]) if len(series) > 1 else last_val
            is_up = last_val >= prev_val
            color = _GREEN if is_up else _RED

            fig = go.Figure(go.Scatter(
                x=list(range(len(series))), y=series.values,
                line=dict(color=color, width=1.5),
                fill="tozeroy",
                fillcolor=f"rgba({'38,166,154' if is_up else '239,83,80'},0.07)",
            ))
            fig.update_layout(
                paper_bgcolor=_CARD, plot_bgcolor=_CARD,
                margin=dict(l=0, r=0, t=0, b=0),
                height=60,
                xaxis=dict(visible=False),
                yaxis=dict(visible=False),
                showlegend=False,
            )

            st.markdown(
                f"""
                <div style="background:{_CARD};border:1px solid {_GRID};
                            border-radius:6px;padding:10px 12px 4px;margin-bottom:4px;">
                    <div style="font-size:10px;color:{_MUTED};letter-spacing:0.8px;
                                text-transform:uppercase;">{labels_map.get(feat, feat)}</div>
                    <div style="font-size:18px;font-weight:700;color:{color};">
                        {last_val:+.4f}
                    </div>
                """,
                unsafe_allow_html=True,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown("</div>", unsafe_allow_html=True)


def render(ticker: str, **_kwargs) -> None:
    st.markdown(
        '<h2 style="margin:0 0 20px;color:#d1d4dc;font-size:20px;font-weight:700;">'
        'Intelligence Artificielle & Signaux ML</h2>',
        unsafe_allow_html=True,
    )

    with st.spinner("Analyse ML en cours-?-"):
        ml = get_ml_analysis(ticker)

    bull_prob     = ml["bull_probability"]
    signal_label  = ml["signal_label"]
    model_avail   = ml["model_available"]
    accuracy      = ml["accuracy"]
    importances   = ml["feature_importance"]
    latest        = ml["latest_features"]
    features_df   = ml["features_df"]

    # -"?-"? Bannière modèle manquant -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    if not model_avail:
        st.warning(
            "-s- Modèle ML non entraîné pour ce ticker. "
            "Lancez `python main.py` pour entraîner le RandomForest. "
            "Les indicateurs techniques restent disponibles.",
            icon=None,
        )

    # -"?-"? Signal principal -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Signal ML Actuel")
    sig_col, gauge_col = st.columns([1, 2])

    with sig_col:
        signal_badge(signal_label)

        if model_avail:
            kpi_card("Probabilité Haussière", f"{bull_prob*100:.1f}%",
                     f"Confiance modèle : {'haute' if abs(bull_prob-0.5)>0.1 else 'faible'}",
                     bull_prob > 0.5, _GREEN if bull_prob > 0.5 else _RED)
            st.markdown('<div style="margin:12px 0;"></div>', unsafe_allow_html=True)
            if accuracy is not None:
                kpi_card("Accuracy (test)", f"{accuracy*100:.1f}%",
                         "Sur 20% des données hors-entraînement",
                         accuracy >= 0.5, _GREEN if accuracy >= 0.55 else _ORANGE)
        else:
            st.markdown(
                f'<div style="color:{_MUTED};font-size:13px;margin-top:8px;">'
                "Entraînez d'abord le modèle.</div>",
                unsafe_allow_html=True,
            )

    with gauge_col:
        st.plotly_chart(
            bull_probability_gauge(bull_prob if model_avail else 0.5),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    divider()

    # -"?-"? Confiance visuelle -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Niveau de Confiance")
    _confidence_bar(bull_prob if model_avail else 0.5)

    divider()

    # -"?-"? Features actuelles -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Indicateurs Techniques Actuels")
    _feature_sparklines(features_df)

    divider()

    # -"?-"? Importance des features -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    if importances:
        section_title("Importance des Features (Random Forest)")
        st.plotly_chart(
            feature_importance_chart(importances),
            use_container_width=True,
            config={"displayModeBar": False},
        )
        divider()

    # -"?-"? RSI -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("RSI 14 (100 dernières barres)")
    st.plotly_chart(
        rsi_chart(features_df),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    divider()

    # -"?-"? Tableau des features -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    section_title("Valeurs Actuelles des Features")
    col_feat, col_explain = st.columns([1, 1])

    with col_feat:
        features_table(latest)

    with col_explain:
        st.markdown(
            f"""
            <div style="background:{_CARD};border:1px solid {_GRID};border-radius:8px;
                        padding:16px 20px;font-size:12px;color:{_MUTED};line-height:1.8;">
                <div style="color:{_TEXT};font-weight:600;margin-bottom:10px;">
                    Interprétation des Features
                </div>
                <b style="color:{_TEXT};"—" Rendement quotidien du prix de clôture.<br>
                <b style="color:{_TEXT};"—" Rendement sur la semaine glissante.<br>
                <b style="color:{_TEXT};"—" Moyennes mobiles simples 20j et 50j.<br>
                <b style="color:{_TEXT};"—" MA20/MA50 : >1 = tendance haussière.<br>
                <b style="color:{_TEXT};"—" RSI 14j : >70 = surachat, <30 = survente.<br>
                <b style="color:{_TEXT};"—" -?cart-type des rendements sur 20j.<br>
                <b style="color:{_TEXT};"—" Variation du volume vs veille.<br>
                <br>
                <span style="color:{_RED};font-weight:600;">-s- Avertissement</span><br>
                Ce modèle est un exemple pédagogique. Les prédictions ne garantissent
                aucun gain et ne constituent pas un conseil financier.
            </div>
            """,
            unsafe_allow_html=True,
        )
