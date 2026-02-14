from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class IndicatorSetup(BaseModel):
    name: str = Field(..., description="MUST be exactly one of the strings from the provided Indicators list.")
    operator: Literal[">", "<", ">=", "<="] = Field(..., description="Comparison operator")
    threshold_value: float = Field(..., description="The numeric threshold value for the condition.")

class Strategy(BaseModel):
    name: str = Field(..., description="Strategy Name")
    rationale: str = Field(..., description="Why this combination?")
    
    indicators: List[IndicatorSetup] = Field(..., min_length=2, max_length=4)
    
    # Risk Settings
    direction: Literal["LONG", "SHORT"] = Field(..., description="Trade Direction")
    stop_loss_pct: float = Field(..., description="Stop Loss % (e.g., 1.5)")
    take_profit_pct: float = Field(..., description="Take Profit % (e.g., 3.0)")

class StrategyBatch(BaseModel):
    strategies: List[Strategy]
