import logging
import pandas as pd
from pathlib import Path
from typing import List
from llm_client import LLMClient
from schemas import StrategyBatch, Strategy
from config import config

logger = logging.getLogger(__name__)

class StrategyGenerator:
    def __init__(self):
        self.llm = LLMClient()
        self.results_file = config.RESULTS_FILE
        self.indicators_file = Path("Indicators.md")

    def get_valid_indicators(self) -> str:
        """Reads the allowed indicators list."""
        if self.indicators_file.exists():
            return self.indicators_file.read_text(encoding="utf-8")
        return "RSI, MACD, Open Interest, Funding Rate" # Fallback

    def get_previous_results_summary(self, top_n=5):
        if not self.results_file.exists(): return "No history."
        try:
            df = pd.read_csv(self.results_file)
            if df.empty: return "No history."
            
            # Clean numeric columns
            # Handle PnL column name variation (net_profit vs cumulative_pnl)
            pnl_col = 'net_profit' if 'net_profit' in df.columns else 'cumulative_pnl'
            
            if pnl_col in df.columns:
                df['net_profit'] = df[pnl_col].astype(str).str.replace('%', '', regex=False)
                df['net_profit'] = pd.to_numeric(df['net_profit'], errors='coerce').fillna(0)
            else:
                logger.warning(f"PnL column not found. Available: {df.columns.tolist()}")
                df['net_profit'] = 0.0

            # Fix for Win Rate format: "12 (60.00%)" -> 60.00
            win_col = 'win_rate' # Assumed constant
            if win_col in df.columns:
                # Extract number inside parentheses if present
                extracted = df[win_col].astype(str).str.extract(r'\((\d+\.?\d*)\%\)')
                # Use original value if extraction failed (no parentheses)
                df['win_rate'] = extracted[0].fillna(df[win_col].astype(str))
                
                # Remove any remaining % symbols and convert
                df['win_rate'] = df['win_rate'].astype(str).str.replace('%', '', regex=False)
                df['win_rate'] = pd.to_numeric(df['win_rate'], errors='coerce').fillna(0)

            # Filter out rows with errors
            df = df[df['status'] != 'ERROR']
            
            if df.empty: return "No valid history."

            best = df.nlargest(top_n, 'net_profit')
            worst = df.nsmallest(top_n, 'net_profit')
            
            summary = "HISTORY (LEARN FROM THIS):\n"
            
            summary += "--- SUCCESSFUL STRATEGIES ---\n"
            for _, row in best.iterrows():
                summary += (
                    f"Name: {row.get('strategy_name')} | Dir: {row.get('direction')} | "
                    f"PnL: {row.get('net_profit')}% | WinRate: {row.get('win_rate')}%\n"
                    f"   TP: {row.get('tp_pct')}% | SL: {row.get('sl_pct')}%\n"
                    f"   Setup: {row.get('indicators_detail')}\n"
                )
                
            summary += "\n--- FAILED STRATEGIES ---\n"
            for _, row in worst.iterrows():
                summary += (
                    f"Name: {row.get('strategy_name')} | PnL: {row.get('net_profit')}% | "
                    f"Setup: {row.get('indicators_detail')}\n"
                )
                
            return summary
        except Exception as e:
            logger.warning(f"Error reading history: {e}")
            return "Error reading history."

    async def generate_strategy_batch(self, batch_size: int = 1) -> List[Strategy]:
        valid_indicators_list = self.get_valid_indicators()
        history = self.get_previous_results_summary()
        
        system_prompt = f"""
        You are an Algorithmic Trader for Hyblock Capital.
        
        AVAILABLE INDICATORS (STRICT LIST):
        {valid_indicators_list}
        
        RULES:
        1. Select BETWEEN 2 AND 4 indicators from the list above. It is NOT required to always use 4.
           - Simple strategies (2 indicators) often have more trades.
           - Complex strategies (4 indicators) are more precise but have fewer trades.
        2. CRITICAL: You must COPY the indicator name EXACTLY as it appears in the list.
           - Do NOT invent new percentages (e.g., do NOT say 'Bids & Asks Ratio - 50%' if only 20% exists).
           - Do NOT shorten names.
        3. Define "operator" (>, <, >=, <=) and "threshold_value" (float).
        4. IMPORTANT: We are using 'Normalize' mode. ALL threshold_values MUST be between 0 and 100.
           - Do NOT use raw values like 100000 or 0.005. 
           - Convert logic to percentile/normalized score (e.g., RSI > 80, Volume Delta > 90).
        5. TIMEFRAME SENSITIVITY:
           - We are trading on **5 Minute (5m)** charts.
           - Signals are noisy. 0 trades often means thresholds are too tight (e.g., RSI > 95 is rare).
           - Relax thresholds to find more trades (e.g., instead of >90, try >80 or >70).
           - RANGE RULE: Ensure Min/Max ranges have at least 5-10 units gap (e.g., 45 to 55, not 50 to 51).
        6. Return a JSON object with a "strategies" list.
        
        EXAMPLE OUTPUT:
        {{
          "strategies": [
            {{
              "name": "Momentum Strategy",
              "rationale": "...",
              "direction": "LONG",
              "stop_loss_pct": 1.5,
              "take_profit_pct": 3.0,
              "indicators": [
                {{ "name": "RSI", "operator": ">", "threshold_value": 70.0 }},
                {{ "name": "Funding Rate", "operator": "<", "threshold_value": 0.01 }},
                {{ "name": "Open Interest", "operator": ">", "threshold_value": 1000.0 }},
                {{ "name": "MACD", "operator": ">", "threshold_value": 0.0 }}
              ]
            }}
          ]
        }}
        """
        
        user_prompt = f"""
        {history}
        
        OBJECTIVE: Find a 'Golden Setup' for BTC/USDT (5m).
        
        PRIORITIES:
        1. **High Trade Count (>50 trades/year):** STRICT REQUIREMENT. Strategies with < 50 trades are marked as SKIPPED/FAILED.
        2. **Positive Expectancy:** Win Rate * Avg Win > Loss Rate * Avg Loss.
        3. **Consistency:** Sharpe Ratio > 1.5 preferred.
        
        INSTRUCTIONS:
        - Analyze the HISTORY above. If a strategy had low trades (0 or <50), LOOSEN the thresholds (e.g. RSI > 60 instead of > 80).
        - If a strategy had high trades but lost money, TIGHTEN the Stop Loss or add a confirmation indicator.
        - Generate {batch_size} NEW strategies. Do NOT repeat failed setups.
        - Output STRICT JSON.
        """
        
        try:
            response = await self.llm.get_completion(system_prompt, user_prompt)
            
            # Debug: Log the raw response if validation fails
            logger.info("Validating LLM response...")
            
            batch = StrategyBatch.model_validate(response)
            
            # Post-Validation: Check if indicators exist in the list
            valid_list = valid_indicators_list.split('\n')
            # Clean list and create case-insensitive map
            valid_list = [i.strip() for i in valid_list if i.strip()]
            valid_map = {i.lower(): i for i in valid_list}
            
            validated_strategies = []
            for strategy in batch.strategies:
                is_valid = True
                for ind in strategy.indicators:
                    # 1. Check lowercase exact match
                    if ind.name.lower() in valid_map:
                        ind.name = valid_map[ind.name.lower()]
                    else:
                        # 2. Try prefix match (Handy for missing [Binance] suffix etc.)
                        # e.g. LLM says "True Retail Long" -> matches "True Retail Long [Binance]"
                        found_match = False
                        for valid_name in valid_list:
                            # Check if valid_name starts with ind.name OR ind.name starts with valid_name (mutual check)
                            if valid_name.lower().startswith(ind.name.lower()) or ind.name.lower().startswith(valid_name.lower()):
                                ind.name = valid_name
                                found_match = True
                                break
                        
                        if not found_match:
                            logger.warning(f"INVALID INDICATOR: '{ind.name}' not in Indicators.md list.")
                            is_valid = False
                            break
                
                if is_valid:
                    validated_strategies.append(strategy)
                else:
                    logger.warning(f"Strategy '{strategy.name}' skipped due to invalid indicators.")
            
            return validated_strategies
            
        except Exception as e:
            logger.error(f"Strategy Gen Failed: {e}")
            logger.error(f"Raw Response causing error might be in debug logs.")
            return []
