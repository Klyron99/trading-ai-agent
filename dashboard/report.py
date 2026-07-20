"""
Génération du rapport de performance en HTML.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime

import pandas as pd
from loguru import logger

from config.settings import DASHBOARD_DIR


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Rapport de Trading — {strategy_name}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; color: #333; }}
  h1 {{ color: #2c3e50; border-bottom: 2px solid #2980b9; padding-bottom: 8px; }}
  h2 {{ color: #2980b9; margin-top: 32px; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 24px; }}
  .card {{
    background: white; border-radius: 8px; padding: 16px 24px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1); min-width: 160px;
  }}
  .card .label {{ font-size: 12px; color: #888; margin-bottom: 4px; }}
  .card .value {{ font-size: 22px; font-weight: bold; }}
  .positive {{ color: #27ae60; }}
  .negative {{ color: #e74c3c; }}
  table {{ width: 100%; border-collapse: collapse; background: white;
           box-shadow: 0 2px 6px rgba(0,0,0,0.08); border-radius: 8px; overflow: hidden; }}
  th {{ background: #2980b9; color: white; padding: 10px 14px; text-align: left; }}
  td {{ padding: 8px 14px; border-bottom: 1px solid #eee; }}
  tr:last-child td {{ border-bottom: none; }}
  .warning {{ background: #fff3cd; border-left: 4px solid #f39c12; padding: 12px 16px;
              border-radius: 4px; margin: 24px 0; }}
  footer {{ margin-top: 40px; font-size: 12px; color: #aaa; text-align: center; }}
</style>
</head>
<body>
<h1>Rapport de Trading — Paper Trading uniquement</h1>
<p>Stratégie : <strong>{strategy_name}</strong> &nbsp;|&nbsp; Ticker : <strong>{ticker}</strong></p>
<p>Généré le {generated_at}</p>

<div class="warning">
  ⚠️ <strong>Avertissement :</strong> Ce rapport est produit dans le cadre du <em>paper trading</em>.
  Il ne constitue pas un conseil financier. Les performances passées ne garantissent pas les
  performances futures.
</div>

<h2>Métriques de performance</h2>
<div class="metrics">
  <div class="card">
    <div class="label">Capital initial</div>
    <div class="value">{capital_initial:.0f} €</div>
  </div>
  <div class="card">
    <div class="label">Capital final</div>
    <div class="value">{capital_final:.0f} €</div>
  </div>
  <div class="card">
    <div class="label">Performance totale</div>
    <div class="value {perf_class}">{performance_totale:+.2f} %</div>
  </div>
  <div class="card">
    <div class="label">Drawdown max</div>
    <div class="value negative">{drawdown_max:.2f} %</div>
  </div>
  <div class="card">
    <div class="label">Sharpe ratio</div>
    <div class="value">{sharpe_ratio:.3f}</div>
  </div>
  <div class="card">
    <div class="label">Nombre de trades</div>
    <div class="value">{nombre_trades}</div>
  </div>
  <div class="card">
    <div class="label">Taux de réussite</div>
    <div class="value">{taux_reussite_pct:.1f} %</div>
  </div>
</div>

<h2>Courbe du capital (50 dernières barres)</h2>
<table>
  <tr><th>Date</th><th>Capital (€)</th><th>Signal</th><th>Prix clôture (€)</th></tr>
  {equity_rows}
</table>

<footer>
  trading_ai_agent — Paper Trading uniquement — Pas de conseil financier
</footer>
</body>
</html>
"""


def generate_html_report(
    equity_curve: pd.DataFrame,
    metrics: dict,
    strategy_name: str,
    ticker: str,
    filename: str | None = None,
) -> Path:
    """Génère un rapport HTML avec les métriques et la courbe du capital.

    Args:
        equity_curve: DataFrame equity_curve du backtester.
        metrics: Dictionnaire de métriques de performance.
        strategy_name: Nom de la stratégie.
        ticker: Symbole boursier.
        filename: Nom du fichier HTML (généré automatiquement si None).

    Returns:
        Chemin vers le fichier HTML créé.
    """
    if filename is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{ticker}_{ts}.html"

    output_path = DASHBOARD_DIR / filename

    # Construit les lignes du tableau (50 dernières barres)
    sample = equity_curve.tail(50)
    signal_labels = {1: "▲ Achat", -1: "▼ Vente", 0: "— Neutre"}
    rows_html = ""
    for date, row in sample.iterrows():
        sig = int(row.get("signal", 0))
        label = signal_labels.get(sig, "—")
        color = "color:#27ae60" if sig == 1 else ("color:#e74c3c" if sig == -1 else "")
        rows_html += (
            f"<tr>"
            f"<td>{date}</td>"
            f"<td>{row['equity']:.2f}</td>"
            f"<td style='{color}'>{label}</td>"
            f"<td>{row.get('price', 0):.2f}</td>"
            f"</tr>\n"
        )

    perf = metrics.get("performance_totale", 0)
    html = _HTML_TEMPLATE.format(
        strategy_name=strategy_name,
        ticker=ticker,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        capital_initial=metrics.get("capital_initial", 0),
        capital_final=metrics.get("capital_final", 0),
        performance_totale=perf,
        perf_class="positive" if perf >= 0 else "negative",
        drawdown_max=metrics.get("drawdown_max", 0),
        sharpe_ratio=metrics.get("sharpe_ratio", 0),
        nombre_trades=metrics.get("nombre_trades", 0),
        taux_reussite_pct=metrics.get("taux_reussite_pct", 0),
        equity_rows=rows_html,
    )

    output_path.write_text(html, encoding="utf-8")
    logger.success(f"Rapport généré : {output_path}")
    return output_path


def export_equity_csv(equity_curve: pd.DataFrame, filename: str = "equity_curve.csv") -> Path:
    """Exporte la courbe du capital en CSV.

    Args:
        equity_curve: DataFrame retourné par Backtester.run().
        filename: Nom du fichier de sortie.

    Returns:
        Chemin vers le fichier CSV créé.
    """
    output_path = DASHBOARD_DIR / filename
    equity_curve.to_csv(output_path, encoding="utf-8")
    logger.info(f"Equity curve exportée : {output_path}")
    return output_path
