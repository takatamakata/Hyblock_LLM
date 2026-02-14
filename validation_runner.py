import asyncio
import pandas as pd
import re
import logging
from schemas import Strategy, IndicatorSetup
from typing import List
from browser_manager import BrowserManager
from backtest_runner import BacktestRunner
from config import config

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("validation_runner.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def parse_indicator_string(ind_string: str) -> List[IndicatorSetup]:
    """
    Parses a string like:
    "Bids & Asks Ratio - 10% > 65.0 | Funding Rate > 5.5 | Volume Delta (10M +) > 60.0"
    into a list of IndicatorSetup objects.
    """
    indicators = []
    # Split by pipe '|'
    parts = ind_string.split('|')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        # Regex to capture Name, Operator, Value
        # Patterns: Name (>|<|>=|<=) Value
        # Example: "Bids & Asks Ratio - 10% > 65.0"
        # Name can contain spaces, %, -, etc.
        match = re.match(r'^(.*?)\s*([><]=?)\s*(\d+\.?\d*)$', part)
        
        if match:
            name = match.group(1).strip()
            operator = match.group(2).strip()
            value = float(match.group(3).strip())
            
            indicators.append(IndicatorSetup(
                name=name,
                operator=operator,
                threshold_value=value
            ))
        else:
            logger.warning(f"Could not parse indicator part: '{part}'")
            
    return indicators

def load_and_filter_strategies(file_path="best_strategies.csv", min_win_rate=40.0) -> List[Strategy]:
    """
    Loads the CSV, filters by win_rate, and parses into Strategy objects.
    """
    logger.info(f"Loading strategies from {file_path}...")
    
    # 1. Load Data (Handle semicolon or comma)
    try:
        # Try semicolon first (as per recent file)
        df = pd.read_csv(file_path, sep=';')
        if len(df.columns) < 5:
            # Fallback to comma if semicolon didn't split well
            logger.info("Semicolon split yielded few columns, trying comma...")
            df = pd.read_csv(file_path, sep=',')
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return []

    logger.info(f"Total strategies loaded: {len(df)}")

    # 2. Clean Win Rate column if needed
    if 'win_rate' in df.columns:
        # Convert "49.28" or "49.28%" to float
        df['win_rate_clean'] = df['win_rate'].astype(str).str.replace('%', '').astype(float)
    else:
        logger.error("Error: 'win_rate' column not found.")
        return []

    # 3. Filter
    filtered_df = df[df['win_rate_clean'] >= min_win_rate].copy()
    logger.info(f"Strategies with Win Rate >= {min_win_rate}%: {len(filtered_df)}")
    
    strategies = []
    
    for index, row in filtered_df.iterrows():
        try:
            # Extract Basic Info
            name = row.get('strategy_name', f"Strategy_{index}")
            direction = row.get('direction', 'LONG').upper()
            tp = float(row.get('tp_pct', 3.0))
            sl = float(row.get('sl_pct', 1.5))
            ind_detail = row.get('indicators_detail', "")
            
            # Parse Indicators
            parsed_indicators = parse_indicator_string(ind_detail)
            
            # Validate indicator count (Schema requires 4, but let's be flexible or pad if needed)
            
            if len(parsed_indicators) == 4:
                strategy_obj = Strategy(
                    name=name,
                    rationale=f"WinRate: {row['win_rate_clean']}% | PnL: {row.get('cumulative_pnl', 0)}",
                    direction=direction,
                    take_profit_pct=tp,
                    stop_loss_pct=sl,
                    indicators=parsed_indicators
                )
                strategies.append(strategy_obj)
            else:
                logger.warning(f"Skipping '{name}': Expected 4 indicators, found {len(parsed_indicators)}.")

        except Exception as e:
            logger.error(f"Error parsing row {index}: {e}")
            continue
            
    return strategies

async def run_validation_loop():
    print("--- STARTING VALIDATION RUNNER ---")
    
    # 1. Load Strategies
    strategies = load_and_filter_strategies()
    
    if not strategies:
        print("No strategies found to validate.")
        return

    # 2. Setup Browser
    bm = BrowserManager()
    runner = BacktestRunner(bm)
    
    # 3. Initialize Browser & Login
    try:
        print("Initializing browser...")
        await bm.setup_browser(headless=False)  # Using visible browser
        
        # Ensure Login
        if not await bm.ensure_login():
            print("Login failed. Aborting.")
            return

        # 4. Validation Loop
        # Timeframes to test
        timeframes = ["15 Min", "5 Min"]
        # Lookbacks to test (Expanded list including 2 Years)
        lookbacks = ["3 Months", "6 Months", "1 Year", "2 Years"] 
        
        results_list = []
        
        # Limit for testing?
        # strategies = strategies[:5] # Uncomment to test only first 5
        
        total_combinations = len(timeframes) * len(lookbacks)
        total_strategies = len(strategies)
        total_runs = total_strategies * total_combinations
        
        current_run = 0

        print(f"Starting validation of {total_strategies} strategies.")
        print(f"Each strategy will be tested on {len(timeframes)} Timeframes x {len(lookbacks)} Lookbacks.")
        
        # Loop Order: Strategy -> Timeframe -> Lookback
        for strategy in strategies:
            print(f"\n=== Validating Strategy: {strategy.name} ===")
            
            for timeframe in timeframes:
                for lookback in lookbacks:
                    current_run += 1
                    print(f"\n--- Run {current_run}/{total_runs}: {strategy.name} [{timeframe} | {lookback}] ---")
                    
                    # Run Strategy
                    try:
                        result = await runner.run_strategy(strategy, timeframe=timeframe, lookback=lookback)
                        
                        # Add validation metadata
                        result['validation_timeframe'] = timeframe
                        result['validation_lookback'] = lookback
                        
                        # Print quick result
                        print(f"Result: PnL: {result.get('cumulative_pnl', 'N/A')} | WinRate: {result.get('win_rate', 'N/A')}%")
                        
                        results_list.append(result)
                        
                        # Save intermediate results
                        save_results(results_list)
                        
                    except Exception as e:
                        logger.error(f"Strategy run failed: {e}")
                        
        print("\n--- VALIDATION COMPLETE ---")
        
    except Exception as e:
        logger.error(f"Fatal Error: {e}")
    finally:
        await bm.close()

def save_results(results):
    try:
        df = pd.DataFrame(results)
        # Save as Excel to avoid column issues
        df.to_excel("validation_results.xlsx", index=False)
        # Also CSV
        df.to_csv("validation_results.csv", index=False, sep=';')
    except Exception as e:
        logger.error(f"Failed to save results: {e}")

if __name__ == "__main__":
    asyncio.run(run_validation_loop())
