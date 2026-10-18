"""
Recherche d'une stratégie sur l'or (gold) avec tout l'historique daily disponible.

Protocole anti-surapprentissage :
  1. Chaque famille de stratégies a ses paramètres choisis en walk-forward
     (5 ans d'entraînement → 1 an de test, glissant).
  2. La famille retenue est choisie UNIQUEMENT sur la période de développement
     (OOS jusqu'au 31/12/2020).
  3. La période 2021 → aujourd'hui est un hold-out : on regarde comment la
     famille retenue s'y comporte, sans rien ré-optimiser.
  4. Confirmation sur un 2e instrument (GLD, l'ETF) avec les mêmes règles.

Usage : python run_gold_backtest.py      → reports/gold_backtest.md
"""
from __future__ import annotations

import itertools
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from backtesting.honest import Costs, metrics, simulate, walk_forward_params
from ml.feature_engineering import compute_rsi
from run_honest_backtest import load

warnings.filterwarnings("ignore")

COSTS = Costs(fee=0.0005, slippage=0.0005)       # 5 + 5 bps par côté
COSTS_2X = Costs(fee=0.0010, slippage=0.0010)
HOLDOUT = pd.Timestamp("2021-01-01")


def vol_scale(df, sig, vt):
    """Ajuste la taille pour viser `vt` de volatilité annualisée (plafonné à 1 = sans levier)."""
    if vt is None:
        return sig
    rv = df["Close"].pct_change().rolling(20).std() * np.sqrt(252)
    return sig * (vt / rv).clip(upper=1.0).fillna(0.0)


def _side(long_cond, short_ok):
    s = long_cond.astype(float)
    return s.where(long_cond, -1.0 if short_ok else 0.0)


# ── Familles de stratégies (toutes causales : valeur connue à la clôture t) ──

def sig_buy_hold(df, vt=None):
    return vol_scale(df, pd.Series(1.0, index=df.index), vt)


def sig_sma(df, n, short, vt=None):
    ma = df["Close"].rolling(n).mean()
    return vol_scale(df, _side(df["Close"] > ma, short).where(ma.notna(), 0.0), vt)


def sig_ma_cross(df, fast, slow, short, vt=None):
    f, s = df["Close"].rolling(fast).mean(), df["Close"].rolling(slow).mean()
    return vol_scale(df, _side(f > s, short).where(s.notna(), 0.0), vt)


def sig_momentum(df, months, short, vt=None):
    r = df["Close"].pct_change(int(months * 21))
    return vol_scale(df, _side(r > 0, short).where(r.notna(), 0.0), vt)


def sig_donchian(df, n, short, vt=None):
    """Cassure du plus haut/bas n jours, sortie sur cassure inverse n/2 jours."""
    hi_n = df["High"].rolling(n).max().shift(1)
    lo_n = df["Low"].rolling(n).min().shift(1)
    hi_x = df["High"].rolling(n // 2).max().shift(1)
    lo_x = df["Low"].rolling(n // 2).min().shift(1)
    c = df["Close"].values
    out, p = np.zeros(len(df)), 0.0
    for i in range(len(df)):
        if np.isnan(hi_n.iat[i]):
            continue
        if p <= 0 and c[i] > hi_n.iat[i]:
            p = 1.0
        elif p >= 0 and c[i] < lo_n.iat[i] and short:
            p = -1.0
        elif p > 0 and c[i] < lo_x.iat[i]:
            p = 0.0
        elif p < 0 and c[i] > hi_x.iat[i]:
            p = 0.0
        out[i] = p
    return vol_scale(df, pd.Series(out, index=df.index), vt)


def sig_rsi_mr(df, entry, exit_, vt=None):
    rsi = compute_rsi(df["Close"], 2).values
    trend = (df["Close"] > df["Close"].rolling(200).mean()).values
    out, inpos = np.zeros(len(df)), False
    for i in range(len(df)):
        if not inpos and trend[i] and rsi[i] < entry:
            inpos = True
        elif inpos and (rsi[i] > exit_ or not trend[i]):
            inpos = False
        out[i] = inpos
    return vol_scale(df, pd.Series(out, index=df.index), vt)


def grid(**axes):
    keys = list(axes)
    return [dict(zip(keys, v)) for v in itertools.product(*axes.values())]


VT = [None, 0.12]
FAMILIES = {
    "Tendance SMA":      (sig_sma,      grid(n=[50, 100, 150, 200], short=[False, True], vt=VT)),
    "Croisement MM":     (sig_ma_cross, grid(fast=[10, 20, 50], slow=[100, 200], short=[False, True], vt=VT)),
    "Momentum":          (sig_momentum, grid(months=[1, 3, 6, 12], short=[False, True], vt=VT)),
    "Breakout Donchian": (sig_donchian, grid(n=[20, 55, 100], short=[False, True], vt=VT)),
    "RSI2 reversion":    (sig_rsi_mr,   grid(entry=[5, 10, 20], exit_=[50, 70], vt=VT)),
}

COLS = ["cagr_%", "sharpe", "t_stat", "max_dd_%", "expo_%", "trades", "frais_tot_%"]


def evaluate(df, tgt, start, end=None):
    d = df.loc[start:end] if end is not None else df.loc[start:]
    return metrics(simulate(d, tgt.reindex(d.index).fillna(0.0), COSTS))


def study(ticker):
    df = load(ticker)
    # barres sans range (O=H=L=C, début de GC=F) : on garde, l'open = close préc. y est neutre
    oos_start = df.index[0] + pd.DateOffset(years=5)
    bh = sig_buy_hold(df)
    targets = {"Buy & hold": (bh, None),
               "Buy & hold vol-ciblé 12 %": (sig_buy_hold(df, 0.12), None)}
    for name, (fn, g) in FAMILIES.items():
        targets[name + " (WF)"] = walk_forward_params(df, fn, g, COSTS)
    rows = []
    for name, (tgt, log) in targets.items():
        dev = evaluate(df, tgt, oos_start, HOLDOUT - pd.Timedelta(days=1))
        ho = evaluate(df, tgt, HOLDOUT)
        full = metrics(simulate(df.loc[oos_start:], tgt.reindex(df.loc[oos_start:].index).fillna(0.0), COSTS_2X))
        rows.append({"stratégie": name,
                     **{f"dev_{k}": dev[k] for k in ("cagr_%", "sharpe", "max_dd_%")},
                     **{f"holdout_{k}": ho[k] for k in ("cagr_%", "sharpe", "max_dd_%", "trades")},
                     "sharpe_2x_frais": full["sharpe"],
                     "derniers_params": log[-1]["params"] if log else "-"})
    return df, oos_start, pd.DataFrame(rows).set_index("stratégie"), targets


def main():
    md = ["# Stratégie gold — recherche sur tout l'historique", "",
          "Exécution à l'ouverture suivante, 5 + 5 bps par côté. Paramètres en walk-forward "
          "(5 ans → 1 an). **dev** = OOS jusqu'à fin 2020 (sert au choix). "
          "**holdout** = 2021 → aujourd'hui (jamais utilisé pour choisir).", ""]
    results = {}
    for ticker in ("GC=F", "GLD"):
        df, oos_start, t, targets = study(ticker)
        results[ticker] = t
        print(f"\n=== {ticker}  {df.index[0].date()} → {df.index[-1].date()}  (OOS dès {oos_start.date()})")
        print(t.drop(columns=["derniers_params"]).to_string())
        md += [f"## {ticker} — données {df.index[0].date()} → {df.index[-1].date()}", "",
               t.to_markdown(), ""]

    # Choix sur la période dev de GC=F uniquement (hors buy & hold)
    dev = results["GC=F"].drop(index=["Buy & hold", "Buy & hold vol-ciblé 12 %"])
    best = dev["dev_sharpe"].idxmax()
    print(f"\nFamille retenue sur la période dev (GC=F) : {best}")
    for tk, t in results.items():
        print(f"  {tk} holdout : {best} sharpe {t.loc[best, 'holdout_sharpe']} "
              f"CAGR {t.loc[best, 'holdout_cagr_%']} % DD {t.loc[best, 'holdout_max_dd_%']} %  | "
              f"buy&hold sharpe {t.loc['Buy & hold', 'holdout_sharpe']} CAGR {t.loc['Buy & hold', 'holdout_cagr_%']} % "
              f"DD {t.loc['Buy & hold', 'holdout_max_dd_%']} %")
    md += [f"**Famille retenue (meilleur Sharpe dev sur GC=F) : {best}**", ""]
    Path("reports").mkdir(exist_ok=True)
    Path("reports/gold_backtest.md").write_text("\n".join(md), encoding="utf-8")
    print("Rapport : reports/gold_backtest.md")


if __name__ == "__main__":
    main()
