import ccxt.async_support as ccxt
import asyncio
import time
import numpy as np

async def calculate_weighted_ratio():
    print("--- Calculating Weighted Order Book Ratio (Smart Depth) ---")
    
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': { 'defaultType': 'future' }
    })
    
    symbol = 'BTC/USDT'
    limit = 5000 # Max limit via standard API endpoints (might need API Key for 5000 on some pairs, but 1000 is safe public)
                 # Note: limit=5000 often requires API Key on Binance Futures. Let's try 1000 first, effectively "Visible Impact Zone".
    
    try:
        # 1. Fetch Data
        print(f"Fetching Order Book for {symbol} (limit={limit})...")
        # Using 1000 first as it's reliable public. 5000 usually needs Auth.
        orderbook = await exchange.fetch_order_book(symbol, limit=1000)
        
        bids = np.array(orderbook['bids']) # [[price, qty], ...]
        asks = np.array(orderbook['asks']) # [[price, qty], ...]
        
        if len(bids) == 0 or len(asks) == 0:
            print("Error: Empty orderbook.")
            return

        mid_price = (bids[0][0] + asks[0][0]) / 2
        print(f"Mid Price: {mid_price:.2f}")
        
        # 2. Define Weight Zones (Dynamic based on price percentage)
        # Zone 1: High Impact (0% - 0.5%) -> Weight 1.0
        # Zone 2: Medium Impact (0.5% - 1.0%) -> Weight 0.5
        # Zone 3: Low Impact (1.0% +) -> Weight 0.2 (up to visible limit)
        
        zones = [
            {'limit': 0.005, 'weight': 1.0, 'name': 'High Impact (0-0.5%)'},
            {'limit': 0.010, 'weight': 0.5, 'name': 'Mid Impact  (0.5-1%)'},
            {'limit': 1.000, 'weight': 0.2, 'name': 'Low Impact  (>1.0%)'} # Catch all remaining
        ]
        
        def calculate_weighted_volume(orders, is_bids=True):
            total_weighted_vol = 0
            total_raw_vol = 0
            
            zone_vols = {z['name']: 0 for z in zones}
            
            for price, qty in orders:
                distance_pct = abs(price - mid_price) / mid_price
                vol = price * qty
                total_raw_vol += vol
                
                weight = 0
                assigned_zone = "Out of Range"
                
                # Find Zone
                for zone in zones:
                    if distance_pct <= zone['limit']:
                        weight = zone['weight']
                        assigned_zone = zone['name']
                        break
                
                # If it exceeded all zones (caught by last one usually), use last
                if weight == 0: 
                     weight = zones[-1]['weight']
                     assigned_zone = zones[-1]['name']

                weighted_vol = vol * weight
                total_weighted_vol += weighted_vol
                zone_vols[assigned_zone] += weighted_vol
                
            return total_weighted_vol, total_raw_vol, zone_vols

        # Calculate
        bid_w_vol, bid_raw, bid_details = calculate_weighted_volume(bids, is_bids=True)
        ask_w_vol, ask_raw, ask_details = calculate_weighted_volume(asks, is_bids=False)
        
        # 3. Results
        print("\n--- Analysis ---")
        print(f"{'Zone':<25} | {'Bid (Weighted)':<15} | {'Ask (Weighted)':<15}")
        print("-" * 60)
        for zone in zones:
            name = zone['name']
            print(f"{name:<25} | ${bid_details[name]:<14,.0f} | ${ask_details[name]:<14,.0f}")
            
        print("-" * 60)
        print(f"{'TOTAL':<25} | ${bid_w_vol:<14,.0f} | ${ask_w_vol:<14,.0f}")
        
        # Ratios
        raw_ratio = (bid_raw / ask_raw) if ask_raw > 0 else 0
        weighted_ratio = (bid_w_vol / ask_w_vol) if ask_w_vol > 0 else 0
        
        # Hyblock style often normalized 0-100 or similar. 
        # Simple Ratio: > 1.0 means Bullish (More Bids)
        # Percentage Ratio: Bids / (Bids + Asks) * 100
        
        raw_pct = (bid_raw / (bid_raw + ask_raw)) * 100
        weighted_pct = (bid_w_vol / (bid_w_vol + ask_w_vol)) * 100
        
        print("\n--- RATIO RESULTS ---")
        print(f"Standard Ratio (Raw Vol): {raw_ratio:.4f} (Bids are {raw_pct:.2f}% of total)")
        print(f"Weighted Ratio (Impact) : {weighted_ratio:.4f} (Bids are {weighted_pct:.2f}% of total)")
        
        if weighted_pct > 65.0:
            print(">>> SIGNAL: BULLISH (Weighted Bids > 65%)")
        elif weighted_pct < 35.0:
            print(">>> SIGNAL: BEARISH (Weighted Asks > 65%)")
        else:
            print(">>> SIGNAL: NEUTRAL")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(calculate_weighted_ratio())

