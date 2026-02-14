# Hyblock_LLM — LLM-driven Hyblock Strategy Backtester

This project automates Hyblock Capital’s **Strategy Simulator** (via Playwright) and uses an LLM (via **OpenRouter**) to generate indicator-based strategies, run backtests, and append results to a CSV file for later analysis.

## What it does (high-level)

- **Generates strategies with an LLM** (`strategy_generator.py`)
  - Picks **2–4 indicators** strictly from `Indicators.md`
  - Uses **Normalize mode** (thresholds must be **0–100**)
  - Targets **BTC/USDT**, **5m timeframe**, **1 year lookback**
- **Runs the strategy on Hyblock UI** (`backtest_runner.py`)
  - Sets base UI options (ticker/timeframe/lookback/normalize)
  - Selects indicators, configures min/max ranges, sets LONG/SHORT + TP/SL
  - Clicks **Test Strategy** and scrapes performance metrics
- **Classifies + persists results** (`analyzer.py`)
  - Writes to `backtest_results.csv`
  - Marks strategies as:
    - `PASS` (profit >= 0 and trades >= 50)
    - `FAIL` (profit < 0)
    - `SKIPPED_LOW_VOLUME` (trades < 50)
    - `ERROR` (UI/automation issues)
- **Runs continuously** (`main.py`)
  - Infinite loop; use **CTRL + C** to stop
  - If the browser hangs, it restarts the session automatically

## Requirements

- **Windows** + **PowerShell**
- **Python 3.10+** recommended
- A Hyblock Capital account (manual login required on first run)
- An OpenRouter API key

Python dependencies are listed in `requirements.txt` (Playwright, pandas, dotenv, openai, pydantic, httpx).

## Setup (Windows / PowerShell)

Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Install dependencies:

```powershell
pip install -r requirements.txt
playwright install
```

## Configuration (.env)

Create a `.env` file in the project root (you can copy `ExampleEnv.txt`).

Example:

```env
OPENROUTER_API_KEY=sk-or-v1-xxxx
HYBLOCK_LOGIN_URL=https://hyblockcapital.com/login
HYBLOCK_TARGET_URL=https://hyblockcapital.com/backtesting-lab/strategy-simulator
HEADLESS_MODE=False
MODEL_NAME=nvidia/nemotron-nano-9b-v2:free
```

Notes:

- `OPENROUTER_API_KEY` is required for LLM strategy generation.
- `MODEL_NAME` is any OpenRouter model identifier (OpenAI-compatible chat completion).
- `HEADLESS_MODE` is parsed as boolean; use `True` or `False`.
- A logged-in browser session is stored in `auth.json` after the first successful login.

## Indicators list (`Indicators.md`)

`Indicators.md` is the strict “allow list” of indicators the LLM may use.

- The generator requires **exact indicator names** as they appear in the file.
- You can replace the contents with another curated list (e.g. your premium list),
  but keep it **one indicator per line**.

## Running the bot

Start the backtest loop:

```powershell
python main.py
```

### First run login flow

On the first run (or if `auth.json` is missing/invalid):

- A Chromium window opens
- The bot navigates to the login page
- You must **log in manually**
- After login, the session is saved to `auth.json` automatically

If you get stuck in a login loop, delete `auth.json` and re-run.

## Outputs

- **Main results file**: `backtest_results.csv`
- **Session storage**: `auth.json`
- **Debug screenshots (on dropdown errors)**: `error_dropdown_*.png`
- **Logs**: console output (and optionally `hyblock_bot.log` if you route logs)

The CSV row contains scraped Hyblock metrics such as:

- `total_trades`, `cumulative_pnl`, `max_drawdown`, `avg_trade_duration`
- `win_rate`, `avg_win_trade`, `profit_ratio`, `sharpe_ratio`
- plus metadata: strategy name, direction, TP/SL, indicators detail, status, error

## How the LLM integration works

The LLM client (`llm_client.py`) uses the OpenAI SDK with:

- Base URL: `https://openrouter.ai/api/v1`
- Model: `MODEL_NAME` from `.env`
- JSON output enforced via `response_format={"type": "json_object"}`

The strategy generator validates the response against Pydantic schemas (`schemas.py`)
and filters out strategies that reference indicators not present in `Indicators.md`.

## Analyzing results (Excel + filtered “best” set)

There are two common ways to analyze results:

### Option A) Use the built-in analyzer helper (recommended command)

`clean_and_analyze.py` exposes a function you can call with your real CSV filename:

```powershell
python -c "from clean_and_analyze import clean_and_analyze; clean_and_analyze('backtest_results.csv', 'best_strategies.xlsx')"
```

This will create:

- `best_strategies.xlsx` and `best_strategies.csv` (filtered “elite” set)
- `backtest_results_cleaned_full.xlsx` and `backtest_results_cleaned_full.csv` (cleaned full dataset)

### Option B) Run the script directly

```powershell
python clean_and_analyze.py
```

If you run it this way, note that the script’s default input filename is currently:

- `backtest_results-old-v1.csv`

So you’ll either want to update that default in `clean_and_analyze.py`,
or prefer Option A above.

## Troubleshooting

- **Bot keeps asking to login**: delete `auth.json` and rerun; make sure you complete manual login.
- **Dropdown selection fails**: check generated `error_dropdown_*.png` screenshots.
- **Strategies show 0 trades / get skipped**: the generator is strict about `>= 50` trades.
  Looser thresholds (still within 0–100 in Normalize mode) typically increase trade count.
- **Headless issues**: try `HEADLESS_MODE=False` to observe the UI.

## Project entrypoints

- `main.py`: orchestrates the infinite backtest loop and restarts sessions on hangs
- `strategy_generator.py`: LLM prompting + validation + indicator allow-list enforcement
- `backtest_runner.py`: Playwright UI automation + metrics scraping
- `analyzer.py`: result classification and CSV persistence
- `clean_and_analyze.py`: offline filtering and export to Excel/CSV

