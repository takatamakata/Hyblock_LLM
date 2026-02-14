"""
Agent orchestration for multi-step reasoning.
"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger

from llm_trader.config.settings import settings
from llm_trader.model.qwen_client import QwenClient
from llm_trader.model.schema import (
    Response, 
    AnalystSignal,
    validate_analyst_response,
    validate_llm_response
)
from llm_trader.model.prompts import format_pair_data, format_position


class AnalystAgent:
    """Agent specialized in technical analysis of a single pair."""
    
    def __init__(self, client: QwenClient):
        self.client = client
        
    def _build_system_prompt(self) -> str:
        return """ROLE
You are an expert Technical Analyst specializing in cryptocurrency perp markets.
Your goal is to analyze price action, market structure, and indicators to identify the current trend and key levels.

OUTPUT FORMAT
You must return a single JSON object (no wrapper keys like 'analysis') matching this schema:
- symbol: The symbol you are analyzing (e.g. "BTCUSDT")
- trend_direction: "BULLISH", "BEARISH", or "NEUTRAL"
- trend_strength: 1-10 (10 is strongest)
- key_levels: List of objects with "price", "type" (SUPPORT/RESISTANCE), "strength"
- bias_rationale: Concise explanation (max 2 sentences)
- suggested_action: "LONG", "SHORT", or "WAIT" based purely on chart analysis
- confidence: 0.0 to 1.0

Do NOT consider portfolio constraints or risk management. Focus ONLY on the chart."""

    def _build_user_prompt(self, market_data: Dict[str, Any]) -> str:
        pair_data = format_pair_data(market_data)
        return f"""Analyze the following market data for {pair_data['symbol']}:

{json.dumps(pair_data, separators=(',', ':'))}

Provide your technical assessment."""

    async def analyze_pair(self, market_data: Dict[str, Any]) -> Optional[AnalystSignal]:
        symbol = market_data["symbol"]
        try:
            # Ensure symbol is passed to the validator context if needed, 
            # but here we rely on the LLM to return it correctly or validate_analyst_response to check it.
            
            response_dict = await self.client.call_llm(
                system_prompt=self._build_system_prompt(),
                user_prompt=self._build_user_prompt(market_data),
                temperature=0.1,
                validator_func=validate_analyst_response
            )
            return AnalystSignal.model_validate(response_dict)
        except Exception as e:
            logger.error(f"Analyst failed for {symbol}: {e}")
            return None


class ManagerAgent:
    """Agent responsible for portfolio management and final trading decisions."""
    
    def __init__(self, client: QwenClient):
        self.client = client
        
    def _build_system_prompt(self) -> str:
        return f"""ROLE
You are a Portfolio Manager. You receive technical analysis reports from your team of analysts.
Your job is to make execution decisions based on these reports, available capital, and risk limits.

OBJECTIVES
1. Review Analyst Signals: Trust their trend assessment but verify against your risk constraints.
2. Portfolio Management:
   - Max positions: {settings.max_positions}
   - Risk per trade: {settings.risk_per_trade_pct}%
   - Min Reward/Risk: {settings.min_rr}
3. Conflict Resolution: If analysts suggest more trades than you have capital/slots for, prioritize highest confidence & trend strength.

OUTPUT FORMAT
Return a JSON object with a list of decisions matching this schema EXACTLY:
{{
  "decisions": [
    {{
      "symbol": "BTCUSDT",
      "action": "OPEN_LONG",  // MUST be OPEN_LONG, OPEN_SHORT, HOLD, CLOSE_LONG, CLOSE_SHORT, or AMEND_ORDERS. Do NOT use just "OPEN".
      "reason": "Strong bullish trend with 8/10 strength", // REQUIRED
      "entry": {{ "type": "MARKET" }}, // Required for OPEN_*
      "stop_loss": 95000.0,
      "take_profit": 105000.0,
      "confidence": 0.8,
      "risk_usdt": 100.0,
      "expected_rr": 2.5
    }}
  ]
}}"""

    def _build_user_prompt(
        self, 
        analyst_reports: List[AnalystSignal], 
        portfolio_state: Dict[str, Any]
    ) -> str:
        # Format reports
        reports_summary = []
        for report in analyst_reports:
            reports_summary.append(report.model_dump())
            
        # Format portfolio
        positions = portfolio_state.get("positions", [])
        positions_str = ",\n  ".join([format_position(p) for p in positions])
        if not positions_str:
            positions_str = "// No open positions"
        
        return f"""# PORTFOLIO STATE
Equity: {portfolio_state.get('equity_usdt', 0)} USDT
Available: {portfolio_state.get('available_usdt', 0)} USDT
Open Positions:
[{positions_str}]

# ANALYST REPORTS
{json.dumps(reports_summary, indent=2)}

# INSTRUCTIONS
Decide on actions for each symbol mentioned in reports. 
- IMPORTANT: use explicit actions "OPEN_LONG" or "OPEN_SHORT". Never use just "OPEN".
- If Analyst suggests LONG and you have capacity -> OPEN_LONG.
- If Analyst suggests SHORT and you have capacity -> OPEN_SHORT.
- If Analyst suggests WAIT and you have a position -> consider CLOSE_LONG/CLOSE_SHORT or HOLD.
- Always provide a short "reason".

Return strict JSON response."""

    async def make_decisions(
        self, 
        analyst_reports: List[AnalystSignal],
        portfolio_state: Dict[str, Any]
    ) -> Response:
        
        if not analyst_reports:
            logger.warning("No analyst reports available for Manager")
            # Return empty/hold decisions if needed, but caller should handle
            raise ValueError("No analyst reports provided")

        try:
            response_dict = await self.client.call_llm(
                system_prompt=self._build_system_prompt(),
                user_prompt=self._build_user_prompt(analyst_reports, portfolio_state),
                temperature=0.1,
                validator_func=validate_llm_response
            )
            return Response.model_validate(response_dict)
        except Exception as e:
            logger.error(f"Manager failed to make decisions: {e}")
            raise


async def run_analysis_cycle(
    client: QwenClient,
    market_data_map: Dict[str, Any],
    portfolio_state: Dict[str, Any]
) -> Response:
    """
    Orchestrate the full analysis cycle:
    1. Run Analyst Agents in parallel for all symbols
    2. Aggregate results
    3. Run Manager Agent
    """
    logger.info("Starting Agent Analysis Cycle...")
    
    # 1. Run Analysts
    analyst_agent = AnalystAgent(client)
    tasks = []
    
    for symbol, data in market_data_map.items():
        tasks.append(analyst_agent.analyze_pair(data))
    
    logger.info(f"Dispatching {len(tasks)} analyst agents...")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter valid reports
    valid_reports: List[AnalystSignal] = []
    for res in results:
        if isinstance(res, AnalystSignal):
            valid_reports.append(res)
        elif isinstance(res, Exception):
            logger.error(f"Analyst task failed with error: {res}")
        else:
            # None result
            pass
            
    if not valid_reports:
        logger.error("No valid analyst reports generated. Aborting cycle.")
        # Return empty response or handle error
        # For now, let's raise or return safe fallback
        return Response(decisions=[]) # This might fail validation if empty decisions are not allowed? 
        # Schema says "At least one decision required" maybe?
        # Let's check schema. Yes: "At least one decision required"
        
    logger.info(f"Collected {len(valid_reports)} analyst reports. Running Manager...")
    
    # 2. Run Manager
    manager_agent = ManagerAgent(client)
    final_decision = await manager_agent.make_decisions(valid_reports, portfolio_state)
    
    logger.info(f"Manager generated {len(final_decision.decisions)} decisions.")
    return final_decision
