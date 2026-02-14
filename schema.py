"""Pydantic schemas for LLM request/response validation."""

from typing import Literal, Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
import json


class Entry(BaseModel):
    """Order entry configuration."""
    
    type: Optional[Literal["LIMIT", "MARKET"]] = Field(
        default=None,
        description="Order type"
    )
    price: Optional[float] = Field(
        default=None,
        ge=0,
        description="Entry price for limit orders"
    )
    
    @field_validator('type', mode='before')
    @classmethod
    def convert_null_string(cls, v):
        """Convert string 'null' to actual None."""
        if v == "null" or v == "":
            return None
        return v


class Decision(BaseModel):
    """Trading decision for a single symbol."""
    
    symbol: str = Field(
        description="Trading symbol (e.g., BTCUSDT)"
    )
    
    action: Literal[
        "HOLD", 
        "OPEN_LONG", 
        "OPEN_SHORT", 
        "CLOSE_LONG", 
        "CLOSE_SHORT", 
        "AMEND_ORDERS"
    ] = Field(
        description="Trading action to take"
    )
    
    entry: Optional[Entry] = Field(
        default=None,
        description="Entry order configuration"
    )
    
    @field_validator('entry', mode='before')
    @classmethod
    def convert_entry(cls, v):
        """Convert null/empty entry to None."""
        if v is None or v == "null" or v == "":
            return None
        # If it's an empty dict, also return None
        if isinstance(v, dict) and not any(v.values()):
            return None
        return v
    
    stop_loss: Optional[float] = Field(
        default=None,
        ge=0,
        description="Stop loss price"
    )
    
    take_profit: Optional[float] = Field(
        default=None,
        ge=0,
        description="Take profit price"
    )
    
    qty: Optional[float] = Field(
        default=None,
        gt=0,
        description="Position quantity"
    )
    
    leverage: Optional[int] = Field(
        default=None,
        ge=1,
        le=125,
        description="Position leverage"
    )
    
    @field_validator('leverage', mode='before')
    @classmethod
    def convert_leverage(cls, v):
        """Convert float leverage to integer by rounding."""
        if v is None or v == "null" or v == "":
            return None
        
        # Convert to integer
        leverage_int = int(round(float(v)))
        
        # If 0 or negative, treat as None (for HOLD/AMEND decisions)
        if leverage_int <= 0:
            return None
        
        return leverage_int
    
    time_in_force: Optional[Literal["GTC", "IOC"]] = Field(
        default=None,
        description="Time in force for orders"
    )
    
    risk_usdt: Optional[float] = Field(
        default=None,
        gt=0,
        description="Risk amount in USDT"
    )
    
    @field_validator('risk_usdt', mode='before')
    @classmethod
    def convert_zero_risk_to_none(cls, v):
        """Convert 0 or 0.0 to None for risk_usdt."""
        if v is None or v == "null" or v == "":
            return None
        # Convert 0 or 0.0 to None (for HOLD/AMEND decisions)
        if float(v) == 0.0:
            return None
        return v
    
    expected_rr: Optional[float] = Field(
        default=None,
        gt=0,
        description="Expected risk-reward ratio"
    )
    
    @field_validator('expected_rr', mode='before')
    @classmethod
    def convert_zero_rr_to_none(cls, v):
        """Convert 0 or 0.0 to None for expected_rr."""
        if v is None or v == "null" or v == "":
            return None
        # Convert 0 or 0.0 to None (for HOLD/AMEND decisions)
        if float(v) == 0.0:
            return None
        return v
    
    confidence: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Confidence level (0-1)"
    )
    
    @field_validator('confidence', mode='before')
    @classmethod
    def convert_confidence(cls, v):
        """Convert percentage (0-100) to decimal (0-1) if needed."""
        if v is None:
            return 0.5
        v = float(v)
        # If value is > 1, assume it's a percentage
        if v > 1:
            return v / 100.0
        return v
    
    ttl_minutes: Optional[int] = Field(
        default=15,
        ge=0,
        description="Time to live for the decision in minutes"
    )
    
    @field_validator('ttl_minutes', mode='before')
    @classmethod
    def convert_null_ttl(cls, v):
        """Convert null to default value."""
        if v is None or v == "null" or v == "":
            return 15  # Default TTL
        
        ttl = int(v)
        
        # If 0, treat as 15 (default) for HOLD decisions
        if ttl == 0:
            return 15
        
        return ttl
    
    reason: str = Field(
        description="Brief explanation for the decision"
    )
    
    @field_validator('time_in_force', mode='before')
    @classmethod
    def convert_null_time_in_force(cls, v):
        """Convert string 'null' to actual None for time_in_force."""
        if v == "null" or v == "":
            return None
        return v
    
    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v):
        """Ensure symbol is uppercase."""
        return v.upper()
    
    @field_validator('action')
    @classmethod
    def validate_action_consistency(cls, v, info):
        """Validate action consistency with other fields."""
        if v in ["OPEN_LONG", "OPEN_SHORT"]:
            # Opening positions should have certain fields
            if info.data.get('entry') is None:
                # Default to market order if not specified
                info.data['entry'] = Entry(type="MARKET")
        return v
    
    def is_opening_position(self) -> bool:
        """Check if this decision opens a new position."""
        return self.action in ["OPEN_LONG", "OPEN_SHORT"]
    
    def is_closing_position(self) -> bool:
        """Check if this decision closes a position."""
        return self.action in ["CLOSE_LONG", "CLOSE_SHORT"]
    
    def is_hold(self) -> bool:
        """Check if this is a hold decision."""
        return self.action == "HOLD"
    
    def get_direction(self) -> Optional[Literal["LONG", "SHORT"]]:
        """Get position direction if applicable."""
        if self.action in ["OPEN_LONG", "CLOSE_LONG"]:
            return "LONG"
        elif self.action in ["OPEN_SHORT", "CLOSE_SHORT"]:
            return "SHORT"
        return None


class Response(BaseModel):
    """Complete LLM response with multiple decisions (Manager Output)."""
    
    decisions: List[Decision] = Field(
        description="List of trading decisions for each symbol"
    )
    
    @field_validator('decisions')
    @classmethod
    def validate_decisions(cls, v):
        """Ensure we have valid decisions."""
        if not v:
            raise ValueError("At least one decision required")
        
        # Check for duplicate symbols
        symbols = [d.symbol for d in v]
        if len(symbols) != len(set(symbols)):
            raise ValueError("Duplicate symbols in decisions")
        
        return v
    
    def get_decision_for_symbol(self, symbol: str) -> Optional[Decision]:
        """Get decision for a specific symbol."""
        symbol = symbol.upper()
        for decision in self.decisions:
            if decision.symbol == symbol:
                return decision
        return None
    
    def get_opening_decisions(self) -> List[Decision]:
        """Get all decisions that open new positions."""
        return [d for d in self.decisions if d.is_opening_position()]
    
    def get_closing_decisions(self) -> List[Decision]:
        """Get all decisions that close positions."""
        return [d for d in self.decisions if d.is_closing_position()]
    
    def to_jsonschema(self) -> dict:
        """Export JSON schema for LLM guidance."""
        return self.model_json_schema()
    
    def to_json(self, **kwargs) -> str:
        """Convert to JSON string."""
        return self.model_dump_json(**kwargs)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Response':
        """Create from JSON string with validation."""
        data = json.loads(json_str)
        return cls.model_validate(data)


# --- New Analyst Agent Schemas ---

class KeyLevel(BaseModel):
    """Support/Resistance level identified by Analyst."""
    price: float
    type: Literal["SUPPORT", "RESISTANCE"]
    # Allow relaxed input (int/str) and validate to strict Literal
    strength: Literal["WEAK", "MODERATE", "STRONG"]
    
    @field_validator('strength', mode='before')
    @classmethod
    def convert_strength(cls, v):
        """Convert integer strength (1-10) or loose strings to strict Literal."""
        # Handle integers (1-10)
        if isinstance(v, int) or (isinstance(v, str) and v.isdigit()):
            val = int(v)
            if val >= 8:
                return "STRONG"
            elif val >= 5:
                return "MODERATE"
            else:
                return "WEAK"
                
        # Handle loose strings (case insensitive, whitespace)
        if isinstance(v, str):
            v_upper = v.upper().strip()
            if v_upper in ["WEAK", "MODERATE", "STRONG"]:
                return v_upper
            # Fallback mappings
            if "HIGH" in v_upper: return "STRONG"
            if "MED" in v_upper: return "MODERATE"
            if "LOW" in v_upper: return "WEAK"
            
        return v  # Let Pydantic raise error if it doesn't match


class AnalystSignal(BaseModel):
    """Single symbol analysis result from Analyst Agent."""
    symbol: str = Field(description="Trading symbol being analyzed")
    trend_direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    trend_strength: int = Field(
        ge=1, 
        le=10, 
        description="Strength of the trend (1-10)"
    )
    key_levels: List[KeyLevel] = Field(
        default_factory=list,
        description="Important support and resistance levels"
    )
    bias_rationale: str = Field(
        description="Short explanation of the technical bias"
    )
    suggested_action: Literal["LONG", "SHORT", "WAIT"] = Field(
        description="Analyst's recommendation based on pure PA"
    )
    confidence: float = Field(
        ge=0,
        le=1,
        description="Confidence in the analysis (0-1)"
    )
    
    def to_jsonschema(self) -> dict:
        """Export JSON schema for LLM guidance."""
        return self.model_json_schema()


# Export JSON schemas
RESPONSE_SCHEMA = Response.model_json_schema()
# Use AnalystSignal directly as the schema
ANALYSIS_SCHEMA = AnalystSignal.model_json_schema()


def validate_llm_response(json_data: dict) -> Response:
    """
    Validate Manager LLM response data.
    
    Args:
        json_data: Parsed JSON from LLM
    
    Returns:
        Validated Response object
    """
    return Response.model_validate(json_data)


def validate_analyst_response(json_data: dict) -> AnalystSignal:
    """
    Validate Analyst LLM response data.
    
    Args:
        json_data: Parsed JSON from LLM
        
    Returns:
        Validated AnalystSignal object
    """
    return AnalystSignal.model_validate(json_data)
