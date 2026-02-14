"""Settings configuration using Pydantic BaseSettings."""

from typing import List, Literal, Optional, Union
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # Allow case-insensitive env var matching
        extra="ignore",  # Ignore extra fields in .env
    )
    
    # Binance API
    binance_um_api_key: str = Field(default="", description="Binance Futures API Key")
    binance_um_api_secret: str = Field(default="", description="Binance Futures API Secret")
    binance_base_url: str = Field(
        default="https://fapi.binance.com", 
        description="Binance Futures base URL"
    )
    binance_testnet_url: str = Field(
        default="https://testnet.binancefuture.com",
        description="Binance Futures testnet URL"
    )
    
    # OpenRouter/LLM
    openrouter_api_key: str = Field(default="", description="OpenRouter API Key")
    openrouter_model: str = Field(default="qwen/qwen-3", description="LLM model to use")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter base URL"
    )
    
    # Trading Configuration
    timezone: str = Field(default="Europe/Istanbul", description="Trading timezone")
    pairs: Union[str, List[str]] = Field(
        default="BTCUSDT,ETHUSDT,XRPUSDT,BNBUSDT,SOLUSDT,DOGEUSDT,TRXUSDT",
        description="List of trading pairs (comma-separated string or list)"
    )
    mode: Literal["paper", "testnet", "live"] = Field(
        default="paper", 
        description="Trading mode"
    )
    
    # Risk Management
    risk_per_trade_pct: float = Field(
        default=0.5, 
        ge=0.1, 
        le=5.0,
        description="Risk per trade as percentage of equity"
    )
    min_rr: float = Field(
        default=1.5, 
        ge=1.0,
        description="Minimum risk-reward ratio"
    )
    min_confidence: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Minimum LLM confidence to execute a trade"
    )
    max_leverage: int = Field(
        default=10, 
        ge=1, 
        le=125,
        description="Maximum allowed leverage"
    )
    maker_fee_bps: float = Field(default=1.0, description="Maker fee in basis points")
    taker_fee_bps: float = Field(default=5.0, description="Taker fee in basis points")
    cooldown_min: int = Field(
        default=5, 
        ge=0,
        description="Cooldown minutes after stop loss"
    )
    min_bars_between_trades: int = Field(
        default=2,
        ge=0,
        description="Minimum bars to wait between trades for same symbol (0 = no restriction)"
    )
    rr_uplift_on_misalignment: float = Field(
        default=0.5,
        ge=0,
        description="Additional RR required when 15m and 4h trends are misaligned"
    )
    
    # Data Parameters
    history_15m_len: int = Field(default=100, ge=10, description="15m history length for calculations")
    history_4h_len: int = Field(default=100, ge=5, description="4h history length for calculations")
    
    # LLM-specific data window (subset of full history to reduce prompt size)
    llm_history_15m_len: int = Field(default=20, ge=5, description="15m history sent to LLM")
    llm_history_4h_len: int = Field(default=20, ge=5, description="4h history sent to LLM")
    
    depth_levels: int = Field(default=5, ge=1, le=20, description="Order book depth levels")
    
    # Feature Toggles
    enable_taker_flow: bool = Field(default=True, description="Enable taker flow analysis")
    enable_orderbook_snapshot: bool = Field(default=True, description="Enable order book data")
    enable_swing_levels: bool = Field(default=True, description="Enable swing level calculation")
    enable_rsi: bool = Field(default=True, description="Enable RSI calculation and sharing with LLM")
    enable_ema: bool = Field(default=True, description="Enable EMA calculation and sharing with LLM")
    enable_macd: bool = Field(default=True, description="Enable MACD calculation and sharing with LLM")
    enable_atr: bool = Field(default=True, description="Enable ATR calculation and sharing with LLM")
    
    # Swing Level Parameters
    swing_left_bars: int = Field(default=2, ge=1, description="Left bars for pivot detection")
    swing_right_bars: int = Field(default=2, ge=1, description="Right bars for pivot detection")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file_rotation: str = Field(default="1 week", description="Log file rotation period")
    log_file_retention: str = Field(default="4 weeks", description="Log file retention period")
    
    # Paths
    storage_path: Path = Field(default=Path("llm_trader/storage"), description="Storage path")
    logs_path: Path = Field(default=Path("llm_trader/storage/logs"), description="Logs path")
    
    # Derived Properties
    @property
    def max_positions(self) -> int:
        """Maximum number of positions (equal to number of pairs)."""
        return len(self.pairs)
    
    @property
    def binance_url(self) -> str:
        """Get appropriate Binance URL based on mode."""
        if self.mode == "testnet":
            return self.binance_testnet_url
        return self.binance_base_url
    
    @field_validator("pairs", mode="before")
    @classmethod
    def parse_pairs(cls, v) -> List[str]:
        """Parse comma-separated pairs string or list."""
        # If already a list, return as is
        if isinstance(v, list):
            return [p.strip().upper() for p in v if p.strip()]
        
        # If string, split by comma
        if isinstance(v, str):
            # Handle empty string
            if not v.strip():
                return ["BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT", "DOGEUSDT", "TRXUSDT"]
            return [p.strip().upper() for p in v.split(",") if p.strip()]
        
        # Fallback to default
        return ["BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT", "DOGEUSDT", "TRXUSDT"]
    
    @field_validator("pairs")
    @classmethod
    def validate_pairs(cls, v) -> List[str]:
        """Validate trading pairs format."""
        if not isinstance(v, list):
            raise ValueError("Pairs must be a list after parsing")
        
        valid_pairs = []
        for pair in v:
            pair = str(pair).strip().upper()
            if not pair.endswith("USDT"):
                raise ValueError(f"Invalid pair {pair}: must end with USDT")
            if len(pair) < 7:  # Minimum: XUSDT
                raise ValueError(f"Invalid pair {pair}: too short")
            valid_pairs.append(pair)
        
        if not valid_pairs:
            raise ValueError("At least one trading pair required")
        
        return valid_pairs
    
    def is_paper_mode(self) -> bool:
        """Check if running in paper mode."""
        return self.mode == "paper"
    
    def is_live_mode(self) -> bool:
        """Check if running in live mode."""
        return self.mode == "live"
    
    def get_fee_rate(self, is_maker: bool = False) -> float:
        """Get fee rate as decimal."""
        fee_bps = self.maker_fee_bps if is_maker else self.taker_fee_bps
        return fee_bps / 10000  # Convert basis points to decimal


# Create singleton instance
settings = Settings()
