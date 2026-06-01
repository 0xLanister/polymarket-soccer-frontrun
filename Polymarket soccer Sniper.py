import time
import requests
from datetime import datetime
from pyclob_client.client import ClobClient
from pyclob_client.clob_types import OrderArgs
from pyclob_client.constants import POLYGON

# ==========================================
# ⚙️ SNIPER CONFIGURATION
# ==========================================

# 1. API-Football Config
SPORTS_API_KEY = "YOUR_API_FOOTBALL_KEY" 
MATCH_ID = "103245" # e.g., Champions League Final Fixture ID

# 2. Polymarket Wallet Config
PRIVATE_KEY = "YOUR_WALLET_PRIVATE_KEY" # Must start with 0x, holds USDC.e and POL
CLOB_HOST = "https://clob.polymarket.com"

# 3. Market Specific Config
# The exact ERC-1155 Token ID for the "YES" outcome you want to buy
TARGET_TOKEN_ID = "123456789012345678901234567890123456789012345678901234567890123456789012345678" 
TRADE_SIZE = 50.0  # Number of shares to buy
MAX_PRICE = 0.85   # Max acceptable price (Limit price acting as Market order)
TARGET_TEAM = "home" # "home" or "away" depending on who you are betting on

# ==========================================

class PolymarketSniper:
    def __init__(self):
        self.current_home_score = 0
        self.current_away_score = 0
        self.trade_executed = False
        
        print(f"[{self._get_time()}] 🔌 Initializing Polymarket CLOB Client...")
        try:
            self.client = ClobClient(
                host=CLOB_HOST, 
                key=PRIVATE_KEY, 
                chain_id=POLYGON
            )
            # Generate and set API credentials for the CLOB
            creds = self.client.create_or_derive_api_creds()
            self.client.set_creds(creds)
            print(f"[{self._get_time()}] ✅ Successfully authenticated with Polymarket.")
        except Exception as e:
            print(f"[{self._get_time()}] ❌ Failed to authenticate: {e}")
            exit(1)

    def _get_time(self):
        """Returns formatted current time for logging."""
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def fetch_live_score(self):
        """Fetches real-time match data from API-Football."""
        url = f"https://v3.football.api-sports.io/fixtures?id={MATCH_ID}"
        headers = {
            "x-apisports-key": SPORTS_API_KEY,
            "x-rapidapi-host": "v3.football.api-sports.io"
        }
        
        try:
            # Using timeout to prevent hanging requests during crucial moments
            response = requests.get(url, headers=headers, timeout=3).json()
            
            if response['errors']:
                print(f"[{self._get_time()}] ⚠️ API Error: {response['errors']}")
                return None

            goals = response['response'][0]['goals']
            
            # API can return None for goals before the match starts
            home = goals.get('home') or 0
            away = goals.get('away') or 0
            
            return {"home": home, "away": away}
            
        except Exception as e:
            print(f"[{self._get_time()}] ⚠️ Network/Fetch Error: {e}")
            return None

    def execute_trade(self, trigger_reason):
        """Executes the buy order on Polymarket CLOB."""
        print("\n" + "🚀" * 20)
        print(f"[{self._get_time()}] 🚨 ALERT! TRIGGER: {trigger_reason}")
        print(f"[{self._get_time()}] 💸 Executing Buy Order on Polymarket...")
        
        try:
            order_args = OrderArgs(
                price=MAX_PRICE,
                size=TRADE_SIZE,
                side="BUY",
                token_id=TARGET_TOKEN_ID
            )
            
            # Sign the payload with the private key
            signed_order = self.client.create_order(order_args)
            
            # Post the order to the matching engine
            response = self.client.post_order(signed_order)
            
            if response and response.get('success'):
                order_id = response.get('orderID', 'UNKNOWN')
                print(f"[{self._get_time()}] ✅ ORDER FILLED / PLACED!")
                print(f"[{self._get_time()}] 📊 Size: {TRADE_SIZE} | Max Price: {MAX_PRICE}")
                print(f"[{self._get_time()}] 🆔 Order ID: {order_id}")
                self.trade_executed = True
            else:
                error_msg = response.get('errorMsg', 'Unknown Error')
                print(f"[{self._get_time()}] ❌ ORDER FAILED: {error_msg}")
                
        except Exception as e:
            print(f"[{self._get_time()}] ❌ CRITICAL EXECUTION ERROR: {e}")
            
        print("🚀" * 20 + "\n")

    def run(self):
        """Main sniper loop."""
        print(f"[{self._get_time()}] 🎯 Sniper active. Monitoring Fixture ID: {MATCH_ID}")
        print(f"[{self._get_time()}] 📡 Target Team: {TARGET_TEAM.upper()} | Polling rate: 1.5s\n")
        
        # Initial score fetch to baseline
        initial_data = self.fetch_live_score()
        if initial_data:
            self.current_home_score = initial_data["home"]
            self.current_away_score = initial_data["away"]
        
        while not self.trade_executed:
            data = self.fetch_live_score()
            
            if data is not None:
                new_home = data["home"]
                new_away = data["away"]
                
                # Check for GOAL condition based on target team
                if TARGET_TEAM == "home" and new_home > self.current_home_score:
                    reason = f"HOME TEAM SCORED! Score changed to {new_home}:{new_away}"
                    self.execute_trade(reason)
                    
                elif TARGET_TEAM == "away" and new_away > self.current_away_score:
                    reason = f"AWAY TEAM SCORED! Score changed to {new_home}:{new_away}"
                    self.execute_trade(reason)
                
                # Update current state
                self.current_home_score = new_home
                self.current_away_score = new_away
                
                print(f"[{self._get_time()}] Monitoring... Current Score: {self.current_home_score}:{self.current_away_score}", end="\r")
            
            # API-Football Pro plan allows faster requests, but 1.5s is safe to avoid instant bans
            time.sleep(1.5) 
            
        print(f"[{self._get_time()}] 🛑 Sniper shutting down safely (Trade already executed).")

if __name__ == "__main__":
    bot = PolymarketSniper()
    bot.run()