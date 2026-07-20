"""Lance l'agent swing gold XAUUSD."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
from dotenv import load_dotenv
load_dotenv()

from agent.gold_swing_agent import GoldSwingAgent

agent = GoldSwingAgent(
    mt5_login=int(os.getenv("MT5_LOGIN", 0)) or None,
    mt5_password=os.getenv("MT5_PASSWORD") or None,
    mt5_server=os.getenv("MT5_SERVER") or None,
)
agent.run()
