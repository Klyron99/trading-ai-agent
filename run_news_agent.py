"""Lance l'agent de trading gold sur annonces économiques."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from agent.news_trading_agent import NewsTradingAgent

agent = NewsTradingAgent(
    mt5_login=int(os.getenv("MT5_LOGIN", 0)) or None,
    mt5_password=os.getenv("MT5_PASSWORD") or None,
    mt5_server=os.getenv("MT5_SERVER") or None,
)
agent.run()
