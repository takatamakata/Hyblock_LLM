import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables
load_dotenv()

class Config(BaseSettings):
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    HYBLOCK_LOGIN_URL: str = os.getenv("HYBLOCK_LOGIN_URL", "https://hyblockcapital.com/login")
    HYBLOCK_TARGET_URL: str = os.getenv("HYBLOCK_TARGET_URL", "https://hyblockcapital.com/backtesting-lab/strategy-simulator")
    HEADLESS_MODE: bool = os.getenv("HEADLESS_MODE", "False").lower() == "true"
    MODEL_NAME: str = os.getenv("MODEL_NAME", "anthropic/claude-3.5-sonnet")
    
    # Browser storage for auth
    AUTH_FILE: Path = Path("auth.json")
    
    # Results
    RESULTS_FILE: Path = Path("backtest_results.csv")
    
    class Config:
        env_file = ".env"
        extra = "ignore"

config = Config()

