import pandas as pd
import re

def clean_and_analyze(input_file="backtest_results-old-v1.csv", output_file="best_strategies.xlsx"):
    print(f"Reading {input_file}...")
    
    try:
        # 1. Read CSV
        # If the file has quoting issues (all in one column), pandas might need specific engine
        # or we might need to manually parse lines if it's very broken.
        # Let's try standard read first, assuming standard CSV format
        df = pd.read_csv(input_file)
        
        # If columns are mashed into one, try separator fix
        if len(df.columns) < 2:
            print("Detected single column issue. Retrying with different separator...")
            df = pd.read_csv(input_file, sep=',', quotechar='"', on_bad_lines='skip')

        print(f"Loaded {len(df)} rows.")
        
        # 2. Clean Data Types
        # Remove % signs and convert to float
        numeric_cols = ['cumulative_pnl', 'max_drawdown', 'win_rate', 'avg_win_trade']
        
        for col in numeric_cols:
            if col in df.columns:
                # Convert "12 (60.00%)" format in win_rate if exists
                if col == 'win_rate':
                    # Extract percentage inside parens if present
                    df[col] = df[col].astype(str).apply(lambda x: re.search(r'\((\d+\.?\d*)%\)', x).group(1) if re.search(r'\((\d+\.?\d*)%\)', x) else x)
                
                # Remove % and convert
                df[col] = df[col].astype(str).str.replace('%', '').str.replace('nan', '0')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Clean trade count
        if 'total_trades' in df.columns:
            df['total_trades'] = pd.to_numeric(df['total_trades'], errors='coerce').fillna(0)

        # 3. Filter for 'PASS' status
        print("Filtering for 'PASS' strategies...")
        if 'status' in df.columns:
            passed_df = df[df['status'].str.strip().str.upper() == 'PASS'].copy()
        else:
            passed_df = df.copy()
            print("Warning: 'status' column not found, using all data.")

        print(f"Found {len(passed_df)} successful strategies.")

        # 4. Advanced Filtering (Your Criteria)
        # Example: Trade > 50, PnL > 0, WinRate > 30
        best_df = passed_df[
            (passed_df['total_trades'] >= 50) & 
            (passed_df['cumulative_pnl'] > 0) &
            (passed_df['win_rate'] >= 30)
        ].copy()

        # 5. Sort by PnL and Sharpe
        if 'sharpe_ratio' in best_df.columns:
             best_df['sharpe_ratio'] = pd.to_numeric(best_df['sharpe_ratio'], errors='coerce').fillna(0)
             best_df = best_df.sort_values(by=['sharpe_ratio', 'cumulative_pnl'], ascending=False)
        else:
             best_df = best_df.sort_values(by='cumulative_pnl', ascending=False)

        print(f"Filtered down to {len(best_df)} 'Elite' strategies.")

        # 6. Save
        # Save as Excel (Preferred for solving column issues)
        best_df.to_excel(output_file, index=False)
        print(f"Saved analysis to {output_file} (Excel format)")

        # Also save as CSV with semicolon separator (common in EU/TR)
        csv_output = output_file.replace('.xlsx', '.csv')
        best_df.to_csv(csv_output, index=False, sep=';')
        print(f"Saved analysis to {csv_output} (CSV with semicolon separator)")
        
        # Also save a clean version of ALL data
        df.to_excel("backtest_results_cleaned_full.xlsx", index=False)
        df.to_csv("backtest_results_cleaned_full.csv", index=False, sep=';')
        print("Saved full cleaned data to backtest_results_cleaned_full.xlsx and .csv (semicolon separated)")

        return best_df

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    clean_and_analyze()
