"""
Composants de métriques KPI pour le dashboard.
Fournit des cartes HTML stylisées et des helpers d'affichage Streamlit.
"""

from __future__ import annotations

import streamlit as st


def kpi_card(
    label: str,
    value: str,
    delta: str = "",
    delta_positive: bool | None = None,
    accent_color: str = "#2962ff",
) -> None:
    """Affiche une carte KPI Bloomberg-style.

    Args:
        label: Titre de la métrique (uppercase automatique).
        value: Valeur principale à afficher.
        delta: Ligne secondaire (variation, comparaison…).
        delta_positive: True → vert, False → rouge, None → gris.
        accent_color: Couleur de la barre verticale gauche.
    """
    if delta_positive is True:
        delta_class = "positive"
        delta_icon = "▲ "
    elif delta_positive is False:
        delta_class = "negative"
        delta_icon = "▼ "
    else:
        delta_class = "neutral"
        delta_icon = ""

    delta_html = (
        f'<div class="kpi-delta {delta_class}">{delta_icon}{delta}</div>'
        if delta
        else ""
    )

    st.markdown(
        f"""
        <div class="kpi-card" style="--accent:{accent_color};">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def signal_badge(signal: int | str) -> None:
    """Affiche un badge de signal coloré (ACHAT / VENTE / NEUTRE)."""
    if isinstance(signal, int):
        label = {1: "▲ ACHAT", -1: "▼ VENTE", 0: "— NEUTRE"}.get(signal, "— NEUTRE")
        css_class = {1: "signal-buy", -1: "signal-sell", 0: "signal-hold"}.get(signal, "signal-hold")
    else:
        s = str(signal).upper()
        if any(k in s for k in ("ACHAT", "BUY", "HAUSS")):
            label, css_class = "▲ ACHAT", "signal-buy"
        elif any(k in s for k in ("VENTE", "SELL", "BAISS")):
            label, css_class = "▼ VENTE", "signal-sell"
        else:
            label, css_class = "— NEUTRE", "signal-hold"

    st.markdown(
        f'<div style="margin:8px 0;"><span class="signal-badge {css_class}">{label}</span></div>',
        unsafe_allow_html=True,
    )


def section_title(text: str) -> None:
    """Affiche un en-tête de section stylisé."""
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)


def status_indicator(mode: str) -> None:
    """Affiche un indicateur de statut animé (LIVE / SIMULATION)."""
    is_live = "ALPACA" in mode.upper() or "LIVE" in mode.upper()
    dot_class = "live" if is_live else "sim"
    color = "#26a69a" if is_live else "#ff9800"
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:8px;font-size:12px;
                    color:{color};font-weight:600;letter-spacing:0.8px;">
            <span class="status-dot {dot_class}"></span>
            {mode.upper()}
        </div>
        """,
        unsafe_allow_html=True,
    )


def divider() -> None:
    st.markdown('<hr style="border:none;border-top:1px solid #1e2433;margin:16px 0;">', unsafe_allow_html=True)


def metric_row(metrics: list[tuple[str, str, str, bool | None]]) -> None:
    """Affiche une rangée de KPI cards.

    Args:
        metrics: liste de (label, value, delta, delta_positive).
    """
    cols = st.columns(len(metrics))
    for col, (label, value, delta, positive) in zip(cols, metrics):
        with col:
            kpi_card(label, value, delta, positive)
