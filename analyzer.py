import pandas as pd
import logging
from pathlib import Path
from config import config

logger = logging.getLogger(__name__)

class Analyzer:
    def __init__(self):
        self.results_file = config.RESULTS_FILE
        # CSV Header Fix based on user observation
        # We ensure the columns match exactly the keys we scrape in backtest_runner
        self.columns = [
            "timestamp", 
            "strategy_name", 
            "direction", 
            "tp_pct", 
            "sl_pct",
            "indicators_detail", 
            "total_trades",      # Was mixed up with win_rate
            "cumulative_pnl",    # Was mixed up with trade_count
            "max_drawdown",
            "avg_trade_duration",
            "win_rate",          # "Trades Won" from Hyblock
            "avg_win_trade",
            "profit_ratio",
            "sharpe_ratio",
            "status", 
            "error"
        ]
        
        if not self.results_file.exists():
            pd.DataFrame(columns=self.columns).to_csv(self.results_file, index=False)

    def process_result(self, result: dict):
        """
        Analyzes the result, updates status, and logs to CSV.
        """
        try:
            # Safe extraction with defaults
            trade_count = int(result.get("total_trades", 0))
            # PnL comes as string "0.05%", convert to float
            pnl_str = str(result.get("cumulative_pnl", "0")).replace("%", "")
            net_profit = float(pnl_str)
        except:
            trade_count = 0
            net_profit = 0.0

        status = result.get("status", "UNKNOWN")

        # Status Logic
        if status == "SUCCESS":
            if trade_count < 50: # STRICT Threshold: Minimum 50 trades required
                result["status"] = "SKIPPED_LOW_VOLUME"
                logger.info(f"Strategy skipped: Low volume ({trade_count} < 50 trades)")
            elif net_profit < 0:
                result["status"] = "FAIL"
                logger.info(f"Strategy failed: Negative profit ({net_profit}%)")
            else:
                result["status"] = "PASS"
                logger.info(f"Strategy PASSED! Profit: {net_profit}%, Trades: {trade_count}")

        # Append to CSV
        try:
            # Create DF with specific column order to ensure CSV matches header
            # Fill missing keys with empty string
            row_data = {col: result.get(col, "") for col in self.columns}
            new_row = pd.DataFrame([row_data])
            
            header = not self.results_file.exists()
            new_row.to_csv(self.results_file, mode='a', header=header, index=False)
            
            logger.info(f"Result saved to {self.results_file}")
        except Exception as e:
            logger.error(f"Failed to save result to CSV: {e}")
