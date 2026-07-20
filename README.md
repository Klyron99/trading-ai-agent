# trading_ai_agent

> **Paper trading uniquement. Aucun ordre réel n'est envoyé.**
> Ce projet est à but pédagogique. Il ne constitue pas un conseil financier.

> 📌 **Dépôt vitrine (portfolio)** — code publié à titre de démonstration.
> Voir [LICENSE](LICENSE) : consultation libre, réutilisation non autorisée.

Agent de trading modulaire en Python avec backtesting, machine learning, gestion du risque et génération de rapports — 100 % simulé.

---

## Table des matières

- [Fonctionnalités](#fonctionnalités)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
- [Tests](#tests)
- [Améliorations futures](#améliorations-futures)
- [Avertissement](#avertissement)

---

## Fonctionnalités

| Module | Description |
|---|---|
| `data/` | Téléchargement OHLCV via yfinance, mise en cache CSV |
| `strategies/` | SMA Crossover (20/50j) et RandomForest ML |
| `ml/` | Feature engineering, entraînement, sauvegarde du modèle |
| `backtesting/` | Backtester maison + métriques (Sharpe, drawdown, taux de réussite) |
| `risk/` | Gestion du risque : 1 % par trade, 20 % max par position, stop loss 5 % |
| `execution/` | Paper broker simulé, gestionnaire d'ordres |
| `logs/` | Logs rotatifs Loguru, export CSV des trades |
| `dashboard/` | Rapport HTML et export CSV de la courbe du capital |

---

## Architecture

```
trading_ai_agent/
├── main.py                      # Point d'entrée principal
├── requirements.txt
├── .env.example
├── config/
│   └── settings.py              # Tous les paramètres centralisés
├── data/
│   ├── market_data.py           # Téléchargement & cache yfinance
│   └── data_cache/              # CSV mis en cache
├── strategies/
│   ├── base_strategy.py         # Classe abstraite
│   ├── moving_average_strategy.py
│   └── ml_strategy.py
├── ml/
│   ├── feature_engineering.py   # Returns, RSI, MA, volatilité…
│   ├── train_model.py           # Entraînement RandomForest
│   └── model_store/             # Modèles .joblib sauvegardés
├── backtesting/
│   ├── backtester.py            # Moteur de simulation
│   └── performance.py           # Sharpe, drawdown, taux réussite
├── risk/
│   └── risk_manager.py          # Validation des ordres
├── execution/
│   ├── paper_broker.py          # Portefeuille simulé
│   └── order_manager.py         # Orchestration signaux → ordres
├── logs/
│   └── trade_logger.py          # Loguru + export CSV
├── dashboard/
│   └── report.py                # Rapport HTML + CSV equity
└── tests/
    ├── conftest.py
    ├── test_strategy.py
    ├── test_risk.py
    └── test_backtester.py
```

---

## Installation

### Prérequis

- Python 3.11 ou supérieur
- pip

### Étapes

```bash
# 1. Cloner ou copier le projet
cd trading_ai_agent

# 2. Créer un environnement virtuel
python -m venv .venv

# 3. Activer l'environnement virtuel
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 4. Installer les dépendances
pip install -r requirements.txt

# 5. Configurer les variables d'environnement
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
# Puis éditer .env selon vos besoins
```

---

## Configuration

Éditez le fichier `.env` pour personnaliser :

```env
INITIAL_CAPITAL=10000.0          # Capital de départ (€)
DEFAULT_TICKERS=AAPL,MSFT,SPY   # Tickers à analyser
DATA_START_DATE=2020-01-01       # Début de l'historique
DATA_END_DATE=2024-12-31         # Fin de l'historique
LOG_LEVEL=INFO                   # Niveau de log

# Alpaca Paper Trading
ALPACA_API_KEY=                  # Clé API Paper (jamais Live)
ALPACA_SECRET_KEY=               # Clé secrète Paper
ALPACA_BASE_URL=https://paper-api.alpaca.markets  # NE PAS MODIFIER
LIVE_TRADING=false               # Doit rester false

# Bot temps réel
LIVE_TICKER=SPY
LIVE_INTERVAL_SEC=60
LIVE_MA_SHORT=5
LIVE_MA_LONG=20
```

Tous les paramètres avancés (fenêtres MA, seuils de risque, hyperparamètres ML) sont dans `config/settings.py`.

---

## Utilisation

### Lancement complet (données + ML + backtests + rapports)

```bash
python main.py
```

Ce script :
1. Télécharge les données pour les tickers configurés
2. Entraîne le modèle RandomForest
3. Lance le backtest SMA Crossover
4. Lance le backtest ML
5. Génère les rapports HTML dans `dashboard/`

### Téléchargement des données uniquement

```python
from data.market_data import download_ohlcv
df = download_ohlcv("AAPL", start="2021-01-01", end="2023-12-31")
print(df.tail())
```

### Entraînement du modèle ML

```python
from data.market_data import download_ohlcv
from ml.train_model import train

df = download_ohlcv("AAPL")
model = train(df, ticker="AAPL")
```

### Backtest d'une stratégie personnalisée

```python
from data.market_data import download_ohlcv
from strategies.moving_average_strategy import MovingAverageStrategy
from backtesting.backtester import Backtester
from backtesting.performance import compute_metrics, print_metrics

df = download_ohlcv("MSFT")
strategy = MovingAverageStrategy(short_window=10, long_window=30)
bt = Backtester(strategy, initial_capital=10_000)
equity = bt.run("MSFT", df)
metrics = compute_metrics(equity, 10_000)
print_metrics(metrics, strategy_name=strategy.name)
```

---

## Lancer le bot en paper trading temps réel

Le bot surveille un ticker en continu, génère des signaux via moyennes mobiles
et envoie des ordres **exclusivement en paper trading** sur Alpaca.

### Prérequis : créer un compte Alpaca Paper

1. Inscrivez-vous sur [alpaca.markets](https://alpaca.markets) (gratuit)
2. Dans le dashboard, sélectionnez **Paper Trading**
3. Récupérez vos clés API Paper (elles commencent par `PK`)
4. Ne jamais utiliser les clés Live ici

### Installation et lancement

```bash
# 1. Installer les dépendances (inclut alpaca-py)
pip install -r requirements.txt

# 2. Configurer l'environnement
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux

# 3. Renseigner les clés Alpaca Paper dans .env
#    ALPACA_API_KEY=PKxxxxxxxxxxxxxxxx
#    ALPACA_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
#    ALPACA_BASE_URL=https://paper-api.alpaca.markets   ← NE PAS MODIFIER
#    LIVE_TRADING=false                                  ← NE PAS MODIFIER

# 4. Lancer le bot
python live_paper_trading.py
```

### Mode simulation (sans clés API)

Si `ALPACA_API_KEY` est vide dans `.env`, le bot démarre automatiquement
en **mode simulation locale** : les prix sont récupérés via yfinance,
les ordres sont exécutés en mémoire. Aucun appel à Alpaca n'est fait.

```bash
# Sans clés API → simulation automatique
python live_paper_trading.py
```

### Sécurités intégrées

| Protection | Comportement |
|---|---|
| `LIVE_TRADING=true` | Arrêt immédiat du programme |
| URL non-paper | Arrêt immédiat avant tout appel réseau |
| Ordre en doublon | Vérification des ordres ouverts, skip si existant |
| Position déjà ouverte | Pas de rachat tant que la position est active |
| Dépassement 20% portefeuille | Bloqué par le RiskManager |
| Risque > 1% par trade | Bloqué par le RiskManager |

### Arrêt propre

```bash
Ctrl+C   # Arrête la boucle proprement après le cycle en cours
```

Les logs sont écrits dans `logs/live_paper_trading.log`.

---

## Tests

```bash
# Lancer tous les tests
pytest tests/ -v

# Avec couverture de code
pytest tests/ -v --cov=. --cov-report=term-missing
```

Les tests couvrent :
- Stratégie SMA (signaux, cas limites)
- Gestion du risque (validation, stop loss, taille de position)
- Backtester (longueur, positivité du capital, métriques)

---

## Améliorations futures

### Intégrations broker
- **Alpaca Paper Trading** : ✅ implémenté dans `execution/alpaca_paper_broker.py`
- **Interactive Brokers** : support TWS API pour des ordres simulés plus réalistes

### Intelligence artificielle
- **Analyse de sentiment** : intégration d'un LLM (Claude, GPT) pour analyser les news financières
- **Reinforcement Learning** : agent RL (PPO, SAC) entraîné sur l'environnement de marché
- **LSTM / Transformer** : modèles de séries temporelles pour améliorer les prédictions

### Optimisation
- **Optuna** : optimisation bayésienne des hyperparamètres (fenêtres MA, seuils de risque)
- **Walk-forward analysis** : validation plus robuste contre l'overfitting

### Infrastructure
- **Dashboard Streamlit** : tableau de bord interactif en temps réel
- **Base de données PostgreSQL** : persistance des trades et de l'historique
- **Alertes Telegram / Discord** : notifications en temps réel sur les signaux
- **Docker** : conteneurisation pour déploiement simplifié
- **CI/CD** : pipeline GitHub Actions pour tests automatiques

---

## Limites du projet

- Les performances du backtest **ne prédisent pas** les performances futures.
- Le modèle ML est un exemple simple — son accuracy ne garantit aucun gain.
- Les frais de transaction, le slippage et la liquidité ne sont pas modélisés.
- Le backtesting peut souffrir de **lookahead bias** si mal configuré — vérifiez toujours la séparation temporelle des données.
- Ce projet ne gère pas la fiscalité, les dividendes ni les splits d'actions.

---

## Avertissement

> **Ce projet est strictement pédagogique.**
> Il ne constitue **pas un conseil financier** et ne doit **pas** être utilisé pour prendre des décisions d'investissement réelles.
> Tout investissement en bourse comporte des risques de perte en capital.
> Les performances passées ne garantissent pas les performances futures.

---

*Développé avec Python 3.11+ — Paper Trading uniquement*
