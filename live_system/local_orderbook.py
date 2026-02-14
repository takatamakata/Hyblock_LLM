import asyncio
import json
import time
import logging
import requests
from websockets import connect
from collections import OrderedDict

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("LocalOrderBook")

class BinanceLocalOrderBook:
    def __init__(self, symbol="btcusdt", depth_range_pct=0.05):
        self.symbol = symbol.lower()
        self.depth_range_pct = depth_range_pct # +/- 5%
        self.ws_url = f"wss://fstream.binance.com/ws/{self.symbol}@depth"
        self.rest_url = f"https://fapi.binance.com/fapi/v1/depth?symbol={self.symbol.upper()}&limit=1000"
        
        self.bids = {}
        self.asks = {}
        self.last_update_id = 0
        self.is_synchronized = False
        self.event_buffer = []
        self.ws = None

    async def start(self):
        """Main entry point to start the Order Book Manager"""
        logger.info(f"Starting Local Order Book for {self.symbol.upper()}...")
        while True:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"WebSocket connection failed: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _connect_and_listen(self):
        async with connect(self.ws_url) as ws:
            self.ws = ws
            logger.info("WebSocket Connected.")
            
            # 1. Start buffering events
            # We need to buffer events BEFORE getting the snapshot to ensure no data gap.
            self.event_buffer = []
            self.is_synchronized = False
            
            # Create a task to process messages
            snapshot_task = asyncio.create_task(self._fetch_snapshot_and_sync())
            
            async for message in ws:
                data = json.loads(message)
                
                if not self.is_synchronized:
                    self.event_buffer.append(data)
                else:
                    # Process directly
                    self._process_update(data)

    async def _fetch_snapshot_and_sync(self):
        """Fetches REST snapshot and synchronizes with buffered WS events"""
        try:
            logger.info("Fetching REST Snapshot...")
            # Wait a bit to build up buffer
            await asyncio.sleep(2)
            
            resp = requests.get(self.rest_url)
            if resp.status_code != 200:
                raise Exception(f"REST Error: {resp.text}")
            
            snapshot = resp.json()
            self.last_update_id = snapshot['lastUpdateId']
            logger.info(f"Snapshot received. LastUpdateId: {self.last_update_id}")
            
            # Initialize Book
            self.bids = {float(p): float(q) for p, q in snapshot['bids']}
            self.asks = {float(p): float(q) for p, q in snapshot['asks']}
            
            # Replay Buffer
            logger.info(f"Processing {len(self.event_buffer)} buffered events...")
            processed_count = 0
            
            for event in self.event_buffer:
                u = event['u'] # Final Update ID
                U = event['U'] # First Update ID
                
                # Drop any event where u is < lastUpdateId
                if u < self.last_update_id:
                    continue
                
                # The first processed event should have U <= lastUpdateId + 1 AND u >= lastUpdateId + 1
                if U <= self.last_update_id + 1 and u >= self.last_update_id + 1:
                    self._process_update(event)
                    processed_count += 1
                    self.is_synchronized = True
                elif self.is_synchronized:
                    # Check sequence? For simplicity in this version, we trust the stream if started correctly.
                    # Ideally: Check if prev_u + 1 == new_U
                    self._process_update(event)
                    processed_count += 1
                    
            if not self.is_synchronized:
                logger.warning("Could not synchronize snapshot with buffer. Restarting...")
                if self.ws: await self.ws.close()
                return

            logger.info(f"Synchronization Complete! Book is Live. (Processed {processed_count} buffered events)")
            self.event_buffer = [] # Clear buffer

        except Exception as e:
            logger.error(f"Snapshot/Sync Error: {e}")
            if self.ws: await self.ws.close()

    def _process_update(self, data):
        """Updates the local order book dicts"""
        # data['b'] is bids updates [[price, qty], ...]
        for p, q in data.get('b', []):
            price = float(p)
            qty = float(q)
            if qty == 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = qty
                
        # data['a'] is asks updates
        for p, q in data.get('a', []):
            price = float(p)
            qty = float(q)
            if qty == 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = qty
                
        # Update ID tracking (optional for strict checks)
        # self.last_update_id = data['u']

    def get_metrics(self):
        """Calculates the Ratio for the target depth"""
        if not self.bids or not self.asks:
            return None

        # 1. Determine Mid Price
        best_bid = max(self.bids.keys())
        best_ask = min(self.asks.keys())
        mid_price = (best_bid + best_ask) / 2
        
        # 2. Define Range
        min_price = mid_price * (1 - self.depth_range_pct) # -5%
        max_price = mid_price * (1 + self.depth_range_pct) # +5%
        
        # 3. Filter and Sum
        # Optimization: Since dict keys are not sorted, we iterate. 
        # For production high-freq, we'd use SortedDict or similar.
        
        relevant_bids_vol = sum(p * q for p, q in self.bids.items() if p >= min_price)
        relevant_asks_vol = sum(p * q for p, q in self.asks.items() if p <= max_price)
        
        # Calculate Coverage (How deep is our book actually?)
        # Note: Since we started with 1000 limit, we might not HAVE 5% depth yet.
        # We track the min bid and max ask in book.
        current_min_bid = min(self.bids.keys())
        current_max_ask = max(self.asks.keys())
        
        bid_depth_reached = (mid_price - current_min_bid) / mid_price
        ask_depth_reached = (current_max_ask - mid_price) / mid_price
        
        return {
            "mid_price": mid_price,
            "bid_vol": relevant_bids_vol,
            "ask_vol": relevant_asks_vol,
            "ratio": (relevant_bids_vol / relevant_asks_vol) if relevant_asks_vol > 0 else 0,
            "bid_pct": (relevant_bids_vol / (relevant_bids_vol + relevant_asks_vol) * 100) if (relevant_bids_vol + relevant_asks_vol) > 0 else 0,
            "bid_depth_reached": bid_depth_reached,
            "ask_depth_reached": ask_depth_reached,
            "total_entries": len(self.bids) + len(self.asks)
        }

async def main_loop():
    # Initialize
    book = BinanceLocalOrderBook(symbol="BTCUSDT", depth_range_pct=0.05)
    
    # Start Book in Background
    asyncio.create_task(book.start())
    
    logger.info("Waiting for data stream to stabilize...")
    await asyncio.sleep(10) 
    
    print("\n" + "="*80)
    print(f"LOCAL ORDER BOOK MONITOR (Target: +/- {book.depth_range_pct*100}%)")
    print("="*80)
    
    # Reporting Loop (Every 5 Minutes - Simulated faster for test: 10 seconds)
    # Changed to 10s for immediate feedback, user can change to 300s
    report_interval = 10 
    
    while True:
        await asyncio.sleep(report_interval)
        
        metrics = book.get_metrics()
        if metrics:
            t = time.strftime("%H:%M:%S")
            print(f"\n[{t}] Price: ${metrics['mid_price']:.2f}")
            print(f"entries: {metrics['total_entries']}")
            print(f"Depth Reached: -{metrics['bid_depth_reached']*100:.2f}% / +{metrics['ask_depth_reached']*100:.2f}%")
            
            if metrics['bid_depth_reached'] < 0.045 or metrics['ask_depth_reached'] < 0.045:
                print(f"WARNING: Book not yet deep enough for full 5% analysis.")
            
            print(f"Bids Vol ({metrics['bid_depth_reached']*100:.1f}%): ${metrics['bid_vol']:,.0f}")
            print(f"Asks Vol ({metrics['ask_depth_reached']*100:.1f}%): ${metrics['ask_vol']:,.0f}")
            print(f"RATIO: {metrics['ratio']:.4f}")
            print(f"BID %: {metrics['bid_pct']:.2f}%")
            
            if metrics['bid_pct'] > 65:
                print(">>> BULLISH SIGNAL")
            elif metrics['bid_pct'] < 35:
                print(">>> BEARISH SIGNAL")
            else:
                print(">>> NEUTRAL")
            print("-" * 40)
        else:
            print("Waiting for sync...")

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("Stopping...")

