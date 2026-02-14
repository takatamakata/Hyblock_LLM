import ccxt.async_support as ccxt
import asyncio
import pandas as pd
import time

async def test_depth_coverage():
    print("--- Testing Binance Depth Coverage ---")
    
    # Initialize Binance
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',  # We are interested in Futures (BTCUSDT)
        }
    })
    
    symbol = 'BTC/USDT'
    target_depth_pct = 0.10 # 10%
    limit = 1000 # Standard limit. Max is usually 1000 via public API, 5000 via some endpoints but heavier.
    
    try:
        print(f"Fetching ticker for {symbol}...")
        ticker = await exchange.fetch_ticker(symbol)
        last_price = ticker['last']
        print(f"Last Price: {last_price} USDT")
        
        # Calculate target price ranges
        lower_bound = last_price * (1 - target_depth_pct)
        upper_bound = last_price * (1 + target_depth_pct)
        print(f"Target 10% Range: {lower_bound:.2f} to {upper_bound:.2f} USDT")
        
        # Fetch Order Book
        # Note: Standard public API limit is 1000.
        # Some endpoints support up to 5000 (limit=5000).
        print(f"Fetching Order Book (limit={limit})...")
        orderbook = await exchange.fetch_order_book(symbol, limit=limit)
        
        bids = orderbook['bids'] # List of [price, qty]
        asks = orderbook['asks'] # List of [price, qty]
        
        print(f"Received {len(bids)} bids and {len(asks)} asks.")
        
        # Analyze Coverage
        min_bid = bids[-1][0] if bids else last_price
        max_ask = asks[-1][0] if asks else last_price
        
        bid_depth_pct = (last_price - min_bid) / last_price
        ask_depth_pct = (max_ask - last_price) / last_price
        
        print("\n--- Coverage Results ---")
        print(f"Deepest Bid: {min_bid:.2f} ({bid_depth_pct*100:.4f}% from price)")
        print(f"Highest Ask: {max_ask:.2f} ({ask_depth_pct*100:.4f}% from price)")
        
        if bid_depth_pct >= target_depth_pct and ask_depth_pct >= target_depth_pct:
            print("SUCCESS: 10% Depth IS reachable with standard snapshot.")
        else:
            print(f"WARNING: Could NOT reach 10% depth with limit={limit}.")
            print(f"To reach 10%, we need ~{target_depth_pct / bid_depth_pct * limit:.0f} entries (estimated).")
            
        # Calculate volume within the available range (just to see data)
        # Bids & Asks Ratio Calculation for available depth
        total_bids_vol = sum([b[0] * b[1] for b in bids])
        total_asks_vol = sum([a[0] * a[1] for a in asks])
        
        print(f"\nTotal Visible Bid Vol: ${total_bids_vol:,.2f}")
        print(f"Total Visible Ask Vol: ${total_asks_vol:,.2f}")
        
        ratio = (total_bids_vol - total_asks_vol) / (total_bids_vol + total_asks_vol) * 100
        # Or simple ratio: bids / asks
        simple_ratio = total_bids_vol / total_asks_vol if total_asks_vol > 0 else 0
        
        print(f"Simple Ratio (Bids/Asks): {simple_ratio:.4f}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_depth_coverage())

