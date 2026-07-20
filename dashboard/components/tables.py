"""
Composants de tableaux stylisés pour le dashboard.
"""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st


# ── Couleurs pour le coloriage conditionnel ───────────────────────────────────
_GREEN_BG = "background-color: rgba(38,166,154,0.12); color: #26a69a"
_RED_BG   = "background-color: rgba(239,83,80,0.12);  color: #ef5350"
_MUTED    = "color: #787b86"


def _color_pnl(val: float | None) -> str:
    if val is None or pd.isna(val):
        return _MUTED
    return _GREEN_BG if val > 0 else _RED_BG if val < 0 else _MUTED


def _color_side(val: str) -> str:
    if "ACHAT" in str(val).upper() or "BUY" in str(val).upper():
        return _GREEN_BG
    if "VENTE" in str(val).upper() or "SELL" in str(val).upper():
        return _RED_BG
    return ""


def trades_table(orders: list[dict], key: str = "trades") -> None:
    """Affiche l'historique des ordres avec filtrage et export CSV."""
    if not orders:
        st.info("Aucun trade enregistré pour cette simulation.")
        return

    df = pd.DataFrame(orders)

    # ── Filtres ──
    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
        sides = ["Tous"] + sorted(df["Sens"].unique().tolist())
        side_filter = st.selectbox("Sens", sides, key=f"{key}_side")
    with col2:
        tickers = ["Tous"] + sorted(df["Ticker"].unique().tolist())
        ticker_filter = st.selectbox("Ticker", tickers, key=f"{key}_ticker")
    with col3:
        pnl_filter = st.checkbox("Uniquement trades avec PnL", key=f"{key}_pnl")

    filtered = df.copy()
    if side_filter != "Tous":
        filtered = filtered[filtered["Sens"] == side_filter]
    if ticker_filter != "Tous":
        filtered = filtered[filtered["Ticker"] == ticker_filter]
    if pnl_filter:
        filtered = filtered[filtered["PnL ($)"].notna()]

    st.caption(f"{len(filtered)} trades affichés sur {len(df)}")

    # ── Styler ──
    numeric_cols = [c for c in ["Prix ($)", "Valeur ($)", "PnL ($)"] if c in filtered.columns]

    styled = (
        filtered.style
        .applymap(_color_pnl, subset=["PnL ($)"] if "PnL ($)" in filtered.columns else [])
        .applymap(_color_side, subset=["Sens"])
        .format({
            "Prix ($)":   "${:,.2f}",
            "Valeur ($)": "${:,.2f}",
            "PnL ($)":    lambda v: f"${v:+,.2f}" if pd.notna(v) else "—",
        }, na_rep="—")
        .set_properties(**{"font-size": "12px"})
    )

    st.dataframe(styled, use_container_width=True, height=400)

    # ── Export CSV ──
    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇ Exporter CSV",
        data=csv,
        file_name="trades_export.csv",
        mime="text/csv",
        key=f"{key}_download",
    )


def positions_table(positions: list[dict]) -> None:
    """Affiche les positions ouvertes avec PnL coloré."""
    if not positions:
        st.info("Aucune position ouverte en fin de simulation.")
        return

    df = pd.DataFrame(positions)

    pnl_col = "PnL latent ($)"
    pct_col = "PnL latent (%)"

    def _row_color(row: pd.Series) -> list[str]:
        styles = [""] * len(row)
        pnl = row.get(pnl_col, 0)
        base = _GREEN_BG if pnl > 0 else _RED_BG if pnl < 0 else _MUTED
        for i, col in enumerate(row.index):
            if col in (pnl_col, pct_col):
                styles[i] = base
        return styles

    fmt: dict = {}
    if "Prix moy. ($)"    in df.columns: fmt["Prix moy. ($)"]    = "${:,.2f}"
    if "Prix actuel ($)"  in df.columns: fmt["Prix actuel ($)"]  = "${:,.2f}"
    if "Valeur ($)"       in df.columns: fmt["Valeur ($)"]       = "${:,.2f}"
    if pnl_col            in df.columns: fmt[pnl_col]            = "${:+,.2f}"
    if pct_col            in df.columns: fmt[pct_col]            = "{:+.2f}%"

    styled = (
        df.style
        .apply(_row_color, axis=1)
        .format(fmt)
        .set_properties(**{"font-size": "12px"})
    )
    st.dataframe(styled, use_container_width=True)


def metrics_summary_table(metrics: dict) -> None:
    """Affiche les métriques clés sous forme de tableau compact."""
    rows = [
        ("Capital initial",     f"${metrics.get('capital_initial', 0):,.2f}"),
        ("Capital final",       f"${metrics.get('capital_final', 0):,.2f}"),
        ("Performance totale",  f"{metrics.get('performance_totale', 0):+.2f}%"),
        ("Drawdown maximum",    f"{metrics.get('drawdown_max', 0):.2f}%"),
        ("Sharpe ratio",        f"{metrics.get('sharpe_ratio', 0):.3f}"),
        ("Nombre de trades",    str(metrics.get('nombre_trades', 0))),
        ("Taux de réussite",    f"{metrics.get('taux_reussite_pct', 0):.1f}%"),
    ]
    df = pd.DataFrame(rows, columns=["Métrique", "Valeur"])
    st.dataframe(df.set_index("Métrique"), use_container_width=True)


def features_table(latest: dict[str, float]) -> None:
    """Affiche les valeurs actuelles des features ML."""
    clean = {k: v for k, v in latest.items() if v is not None and pd.notna(v)}
    rows = [(k, f"{v:+.6f}" if abs(v) < 0.01 else f"{v:,.4f}") for k, v in clean.items()]
    df = pd.DataFrame(rows, columns=["Feature", "Valeur actuelle"])
    st.dataframe(df.set_index("Feature"), use_container_width=True)
