import asyncio
import websockets
import json
import logging
import os
from datetime import datetime
from pyclob_client.client import ClobClient
from pyclob_client.clob_types import OrderArgs
from pyclob_client.constants import POLYGON

# ==========================================
# ⚙️ HFT INFRASTRUCTURE CONFIGURATION
# ==========================================

# Use Environment Variables for security (Don't hardcode in GitHub)
PRIVATE_KEY = os.getenv("POLYGON_PRIVATE_KEY", "0xYOUR_BURNER_WALLET_KEY")
API_FOOTBALL_WSS = os.getenv("SPORTS_WSS_ENDPOINT", "wss://ws.api-football.com/v3/live")
WSS_API_KEY = os.getenv("SPORTS_API_KEY", "YOUR_API_FOOTBALL_KEY")

# Custom RPC Node to bypass public mempool lag (Crucial for Gas Wars)
CUSTOM_RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY")

# Polymarket CLOB Host
CLOB_HOST = "https://clob.polymarket.com"

# --- MARKET ROUTING (Target Tokens) ---
# In a real dynamic system, these would be fetched via Gamma API based on the Fixture ID.
MARKETS = {
    "OVER_2_5": {"token_id": "123456789012...890", "max_slippage_price": 0.85},
    "TEAM_A_WIN": {"token_id": "987654321098...321", "max_slippage_price": 0.80}
}

TRADE_SIZE = 100.0  # Base size in shares

# ==========================================
# 📊 LOGGING SETUP (Pro-grade formatting)
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("FrontrunnerNode")

# ==========================================
# 🚀 ASYNC FRONTRUNNER CORE
# ==========================================

class PolymarketFrontrunner:
    def __init__(self, fixture_id, target_team_id):
        self.fixture_id = fixture_id
        self.target_team_id = target_team_id
        self.loop = asyncio.get_running_loop()
        self.trade_locked = False # Kill switch to prevent double-spending
        
        logger.info(f"Initializing Web3 Frontrunner for Fixture: {self.fixture_id}")
        self._init_clob_client()

    def _init_clob_client(self):
        """Initializes the Polymarket CLOB client using the Custom RPC."""
        try:
            # We override the default RPC to our dedicated node to win mempool gas wars
            self.client = ClobClient(
                host=CLOB_HOST, 
                key=PRIVATE_KEY, 
                chain_id=POLYGON
            )
            creds = self.client.create_or_derive_api_creds()
            self.client.set_creds(creds)
            logger.info("Connected to Polymarket CLOB Engine successfully.")
        except Exception as e:
            logger.error(f"CLOB Authentication failed: {e}")
            raise SystemExit(1)

    async def execute_trade(self, market_key, side, reason):
        """
        Executes the trade on the Polymarket CLOB.
        Uses asyncio.to_thread to prevent the synchronous pyclob-client 
        from blocking the main WebSocket event loop.
        """
        if self.trade_locked:
            logger.warning(f"Trade locked. Ignoring signal: {reason}")
            return
            
        self.trade_locked = True
        token_id = MARKETS[market_key]["token_id"]
        max_price = MARKETS[market_key]["max_slippage_price"]
        
        logger.warning(f"🚨 ALPHA SIGNAL DETECTED: {reason}")
        logger.info(f"Sweeping liquidity... Side: {side} | Market: {market_key} | Max Price: {max_price}")

        # Constructing the Order
        order_args = OrderArgs(
            price=max_price,
            size=TRADE_SIZE,
            side=side,
            token_id=token_id
        )

        try:
            # Sign order (CPU bound, run in executor)
            signed_order = await asyncio.to_thread(self.client.create_order, order_args)
            
            # Post order to matching engine (I/O bound, run in executor)
            # NOTE: In a true HFT setup, priority gas fees (Gwei) would be injected here 
            # if we were calling the L1/L2 contract directly instead of the off-chain CLOB.
            response = await asyncio.to_thread(self.client.post_order, signed_order)
            
            if response and response.get('success'):
                logger.info(f"✅ EXECUTED! Order ID: {response.get('orderID')}")
                logger.info("Now we wait 30 seconds for the TV broadcast to catch up. 🍿")
            else:
                logger.error(f"❌ EXECUTION FAILED. Orderbook rejected: {response.get('errorMsg')}")
                self.trade_locked = False # Unlock on failure to retry
                
        except Exception as e:
            logger.error(f"❌ CRITICAL ROUTING ERROR: {e}")
            self.trade_locked = False

    async def parse_event(self, event):
        """
        The core logic engine. Evaluates real-time JSON payloads against Attack Vectors.
        """
        event_team_id = event.get('team', {}).get('id')
        event_type = event.get('type')
        event_detail = event.get('detail')

        # Ignore events for other matches in the multiplex stream
        if str(event.get('fixture_id')) != str(self.fixture_id):
            return

        # 🔪 Attack Vector 1: Total Sniper (Over/Under)
        if event_type == 'Goal' and event_detail == 'Normal Goal':
            reason = f"GOAL SCORED by Team {event_team_id} at stadium!"
            # Instantly buy YES on OVER 2.5
            asyncio.create_task(self.execute_trade("OVER_2_5", "BUY", reason))

        # 🔪 Attack Vector 2: Penalty Intercept (VAR Arbitrage)
        elif event_type == 'Var' and event_detail == 'Penalty Awarded':
            if event_team_id == self.target_team_id:
                reason = "PENALTY AWARDED (Pre-broadcast anticipation pump)"
                # Buy YES on the team to win (sell later on the pump, even if they miss)
                asyncio.create_task(self.execute_trade("TEAM_A_WIN", "BUY", reason))

        # 🔪 Attack Vector 3: Red Card Squeeze
        elif event_type == 'Card' and event_detail == 'Red Card':
            if event_team_id == self.target_team_id:
                reason = "RED CARD to Target Team. Tanking win probability."
                # Buy NO (which is equivalent to shorting the team's YES shares)
                # Note: 'SELL' in CLOB means selling YES shares. To buy NO, you must target the NO token_id with a 'BUY'. 
                # For simplicity here, we execute a 'SELL' to dump our current bags, or buy the opposite token.
                asyncio.create_task(self.execute_trade("TEAM_A_WIN", "SELL", reason))

    async def stream_listener(self):
        """
        Maintains a persistent WebSocket connection to the sports data provider.
        Bypasses HTTP REST rate limits and latency.
        """
        headers = {"x-apisports-key": WSS_API_KEY}
        
        while True:
            try:
                logger.info(f"Connecting to WSS Endpoint: {API_FOOTBALL_WSS}...")
                async with websockets.connect(API_FOOTBALL_WSS, extra_headers=headers) as websocket:
                    logger.info("🟢 WSS Connected. Listening for real-time stadium events...")
                    
                    # Subscribe to the specific fixture
                    subscribe_payload = json.dumps({"action": "subscribe", "events": ["fixtures"], "fixture_id": self.fixture_id})
                    await websocket.send(subscribe_payload)
                    
                    async for message in websocket:
                        payload = json.loads(message)
                        
                        # Filter heartbeat/ping messages
                        if payload.get("type") == "ping":
                            continue
                            
                        # Route the event asynchronously 
                        await self.parse_event(payload)
                        
            except websockets.ConnectionClosed:
                logger.warning("🔴 WSS Connection dropped. Reconnecting in 1 second...")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Fatal WSS Error: {e}. Retrying...")
                await asyncio.sleep(2)

async def main():
    # Example: Tracking the World Cup Final (Fixture ID: 123456)
    TARGET_FIXTURE = 123456
    TARGET_TEAM = 987 # ID of the team we have a position on

    bot = PolymarketFrontrunner(fixture_id=TARGET_FIXTURE, target_team_id=TARGET_TEAM)
    
    # Run the WebSockets listener forever
    await bot.stream_listener()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Graceful shutdown initiated by user.")
