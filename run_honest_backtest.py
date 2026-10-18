"""
Phase 1 — backtest honnête (frais, glissement, exécution t+1, walk-forward).

Usage :
    python run_honest_backtest.py            # SPY, QQQ daily + ML SPY + ML BTC 1h
    python run_honest_backtest.py --no-btc   # sans le test BTC horaire

Résultats : affichés + écrits dans reports/honest_backtest.md
"""
from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier

from backtesting.honest import Costs, metrics, simulate, walk_forward_ml, walk_forward_params
from ml.feature_engineering import build_features, compute_rsi

warnings.filterwarnings("ignore")

ETF_COSTS = Costs(fee=0.0005, slippage=0.0005)      # 5 + 5 bps par côté
ETF_COSTS_2X = Costs(fee=0.0010, slippage=0.0010)
BTC_COSTS = Costs(fee=0.0010, slippage=0.0005)      # 10 + 5 bps par côté
BTC_COSTS_2X = Costs(fee=0.0020, slippage=0.0010)


def load(ticker: str, interval: str = "1d", period: str = "max") -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval=interval,
                     auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


# ── Stratégies simples (indicateurs causaux, valeur connue à la clôture t) ──

def sig_buy_hold(df):
    return pd.Series(1.0, index=df.index)


def sig_sma(df, n):
    return (df["Close"] > df["Close"].rolling(n).mean()).astype(float)


def sig_momentum(df, months):
    return (df["Close"].pct_change(int(months * 21)) > 0).astype(float)


def sig_rsi_mr(df, entry, exit_):
    """RSI(2) < entry au-dessus de la SMA200 → long, sortie quand RSI(2) > exit_."""
    rsi = compute_rsi(df["Close"], 2).values
    trend = (df["Close"] > df["Close"].rolling(200).mean()).values
    out, inpos = np.zeros(len(df)), False
    for i in range(len(df)):
        if not inpos and trend[i] and rsi[i] < entry:
            inpos = True
        elif inpos and (rsi[i] > exit_ or not trend[i]):
            inpos = False
        out[i] = inpos
    return pd.Series(out, index=df.index)


def sig_ibs(df, thr):
    """Internal Bar Strength bas → long pour la séance suivante."""
    ibs = (df["Close"] - df["Low"]) / (df["High"] - df["Low"]).replace(0, np.nan)
    trend = df["Close"] > df["Close"].rolling(200).mean()
    return ((ibs < thr) & trend).astype(float)


SIMPLE = {
    "SMA trend":     (sig_sma,      [{"n": n} for n in (50, 100, 150, 200, 250)]),
    "Momentum":      (sig_momentum, [{"months": m} for m in (3, 6, 9, 12)]),
    "RSI2 reversion": (sig_rsi_mr,  [{"entry": e, "exit_": x} for e in (5, 10, 15, 25) for x in (50, 70)]),
    "IBS":           (sig_ibs,      [{"thr": t} for t in (0.1, 0.2, 0.3)]),
}


# ── Stratégie ML actuelle, reproduite en walk-forward ───────────────────────

def ml_target(df, horizon, thr):
    fut = df["Close"].shift(-horizon) / df["Close"] - 1
    y = (fut > thr).astype(float)
    y[fut.isna()] = np.nan
    return y


def make_rf():
    return RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=20,
                                  n_jobs=-1, random_state=42)


def ml_signals(proba, long_only):
    sig = pd.Series(0.0, index=proba.index)
    sig[proba >= 0.58] = 1.0
    if not long_only:
        sig[proba <= 0.42] = -1.0
    return sig


def run_ml(df, ticker, horizon, thr, train_bars, step_bars):
    feat = build_features(df, ticker=ticker)
    y = ml_target(df, horizon, thr)
    proba = walk_forward_ml(feat, y, make_rf, train_bars, step_bars, purge_bars=horizon)
    proba = proba.dropna()
    # précision directionnelle OOS
    yy = y.loc[proba.index].dropna()
    acc = ((proba.loc[yy.index] >= 0.5) == (yy == 1)).mean()
    base = yy.mean()
    return proba, acc, base


# ── Rapport ──────────────────────────────────────────────────────────────────

COLS = ["cagr_%", "sharpe", "t_stat", "max_dd_%", "expo_%", "trades", "win_%", "frais_tot_%"]


def row(name, df, target, costs, costs2x):
    m = metrics(simulate(df, target, costs))
    m2 = metrics(simulate(df, target, costs2x))
    return {"stratégie": name, **{k: m[k] for k in COLS},
            "cagr_2x_frais_%": m2["cagr_%"], "sharpe_2x": m2["sharpe"]}


def table(rows):
    return pd.DataFrame(rows).set_index("stratégie")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-btc", action="store_true")
    args = ap.parse_args()

    md = ["# Backtest honnête — phase 1", "",
          "Exécution à l'ouverture suivante, frais + glissement par côté, "
          "paramètres choisis en walk-forward (5 ans d'entraînement → 1 an de test).", ""]

    for ticker in ("SPY", "QQQ"):
        df = load(ticker)
        print(f"\n=== {ticker} daily  {df.index[0].date()} → {df.index[-1].date()} ({len(df)} barres)")
        rows, logs = [], {}
        oos_start = df.index[0] + pd.DateOffset(years=5)
        dft = df.loc[oos_start:]        # même période OOS pour tout le monde
        rows.append(row("Buy & hold", dft, sig_buy_hold(dft), ETF_COSTS, ETF_COSTS_2X))
        for name, (fn, grid) in SIMPLE.items():
            tgt, log = walk_forward_params(df, fn, grid, ETF_COSTS)
            logs[name] = log
            rows.append(row(name + " (WF)", dft, tgt, ETF_COSTS, ETF_COSTS_2X))

        # ML actuelle : horizon 3 j, seuil 0,5 %, ré-entraînée tous les mois sur 2 ans (comme le live)
        print("  ML walk-forward (peut prendre 1-3 min)…")
        proba, acc, base = run_ml(df, ticker, horizon=3, thr=0.005, train_bars=504, step_bars=21)
        proba = proba.loc[oos_start:]
        dfm = df.loc[proba.index]
        rows.append(row("ML actuelle long/short", dfm, ml_signals(proba, False), ETF_COSTS, ETF_COSTS_2X))
        rows.append(row("ML actuelle long only", dfm, ml_signals(proba, True), ETF_COSTS, ETF_COSTS_2X))
        rows.append(row("Buy & hold (même période ML)", dfm, sig_buy_hold(dfm), ETF_COSTS, ETF_COSTS_2X))

        t = table(rows)
        print(t.to_string())
        print(f"  ML : précision OOS {acc:.3f} vs taux de base {max(base, 1-base):.3f}")
        md += [f"## {ticker} daily — OOS {dft.index[0].date()} → {dft.index[-1].date()}", "",
               "Coûts : 5 bps frais + 5 bps glissement par côté (colonnes `_2x` : doublés).", "",
               t.to_markdown(), "",
               f"ML : précision OOS **{acc:.3f}** vs taux de base (toujours prédire la classe majoritaire) "
               f"**{max(base, 1-base):.3f}**.", "",
               "Paramètres choisis par le walk-forward (dernière fenêtre) : " +
               ", ".join(f"{k} → {v[-1]['params']}" for k, v in logs.items()), ""]

    if not args.no_btc:
        df = load("BTC-USD", interval="1h", period="720d")
        print(f"\n=== BTC-USD 1h  {df.index[0]} → {df.index[-1]} ({len(df)} barres)")
        print("  ML walk-forward horaire…")
        # horizon 6 h, seuil 0,3 %, ré-entraînement hebdo sur 6 mois (comme le live)
        proba, acc, base = run_ml(df, "BTC-USD", horizon=6, thr=0.003, train_bars=4380, step_bars=168)
        dfm = df.loc[proba.index]
        rows = [row("Buy & hold", dfm, sig_buy_hold(dfm), BTC_COSTS, BTC_COSTS_2X),
                row("ML actuelle long/short", dfm, ml_signals(proba, False), BTC_COSTS, BTC_COSTS_2X),
                row("ML actuelle long only", dfm, ml_signals(proba, True), BTC_COSTS, BTC_COSTS_2X),
                row("ML sans frais (référence)", dfm, ml_signals(proba, False), Costs(), Costs())]
        t = table(rows)
        print(t.to_string())
        print(f"  ML : précision OOS {acc:.3f} vs taux de base {max(base, 1-base):.3f}")
        md += [f"## BTC-USD 1h — OOS {dfm.index[0].date()} → {dfm.index[-1].date()}", "",
               "Coûts : 10 bps frais + 5 bps glissement par côté.", "",
               t.to_markdown(), "",
               f"ML : précision OOS **{acc:.3f}** vs taux de base **{max(base, 1-base):.3f}**.", ""]

    out = Path("reports")
    out.mkdir(exist_ok=True)
    (out / "honest_backtest.md").write_text("\n".join(md), encoding="utf-8")
    print("\nRapport écrit dans reports/honest_backtest.md")


if __name__ == "__main__":
    main()
