import asyncio
import time
import aiohttp
import logging
from database import (
    get_whales, is_activity_seen, record_activity,
    load_seen_cache, is_activity_seen_fast, mark_activity_seen_fast,
    batch_record_activities, get_whales_cached
)
from bot_engine import send_notification

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

POLYMARKET_API_URL = "https://data-api.polymarket.com/activity"
POLL_INTERVAL = 5

# ============================================================
# CRYPTO-ONLY FILTER - spor/film/diğer betlerini filtrele
# Balinalar sinyal karıştırmak için crypto dışı betler alıyor
# Sadece crypto marketlerini takip ediyoruz
# Word-boundary matching: "op" sadece "OP" kelimesini yakalar,
# "Opening" içindeki "op"u değil
# ============================================================
import re

CRYPTO_KEYWORDS = [
    # Major coins - tam isim ve ticker
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
    "xrp", "ripple", "dogecoin", "doge", "bnb", "binance",
    "hype", "hyperliquid", "cardano", "ada", "polkadot", "dot",
    "avalanche", "avax", "chainlink", "link", "polygon", "matic",
    "litecoin", "ltc", "uniswap", "uni", "aave", "sui",
    "toncoin", "ton", "near", "aptos", "apt", "arbitrum", "arb",
    "optimism", "op", "celestia", "tia", "jupiter", "jup",
    "pepe", "shiba", "shib", "bonk", "wif", "floki",
    "crypto", "coin", "token", "defi",
    # Polymarket crypto market patterns
    "up or down", "above", "below",
]

# Precompile regex: \b ensures word boundary so "op" won't match "Opening"
_CRYPTO_PATTERNS = [
    re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
    for kw in CRYPTO_KEYWORDS
]

def is_crypto_market(title: str) -> bool:
    """Check if a market title is crypto-related using word-boundary matching."""
    if not title:
        return False
    return any(pattern.search(title) for pattern in _CRYPTO_PATTERNS)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache, no-store",
}

def format_telegram_message(wallet: str, trade: dict, nickname: str = None) -> str:
    side = str(trade.get("side") or "UNKNOWN").upper()
    size = float(trade.get("size") or 0)
    price = float(trade.get("price") or 0)
    title = str(trade.get("title") or "Unknown Market")
    outcome = str(trade.get("outcome") or "Unknown Outcome")
    
    import re
    from datetime import datetime

    total_spent = round(size * price, 2)
    
    if outcome.lower() == "up":
        emoji = "🟢"
    elif outcome.lower() == "down":
        emoji = "🔴"
    else:
        emoji = "🔵"
        
    display_title = title
    
    # Extract asset name
    title_lower = title.lower()
    if "bitcoin" in title_lower or "btc" in title_lower:
        asset_name = "Bitcoin"
    elif "ethereum" in title_lower or "eth" in title_lower:
        asset_name = "Ethereum"
    elif "solana" in title_lower or "sol" in title_lower:
        asset_name = "Solana"
    else:
        # Fallback to the first word
        asset_name = title.split(" ")[0]
        
    is_bitcoin = asset_name == "Bitcoin"
    is_5m = False
    
    market_duration = ""
    
    if " - " in title:
        parts = title.split(" - ")
        if len(parts) > 1:
            display_title = f"{parts[0]}"
            time_part = parts[1]
            
            # Try to extract duration
            if "AM" in time_part or "PM" in time_part:
                match = re.search(r'(\d{1,2}:\d{2}[AP]M)-(\d{1,2}:\d{2}[AP]M)', time_part)
                if match:
                    t1_str, t2_str = match.groups()
                    try:
                        t1 = datetime.strptime(t1_str, "%I:%M%p")
                        t2 = datetime.strptime(t2_str, "%I:%M%p")
                        diff = (t2 - t1).total_seconds() / 60
                        if diff < 0: diff += 24*60
                        if diff in [5, 15]:
                            if diff == 5:
                                is_5m = True
                            market_duration = f" {asset_name} {int(diff)} minute"
                    except:
                        pass
                        
            display_title += f"\n⏰ {time_part}"

    if not market_duration:
        if "5-minute" in title.lower() or "5 minute" in title.lower():
            market_duration = f" {asset_name} 5 minute"
            is_5m = True
        elif "15-minute" in title.lower() or "15 minute" in title.lower():
            market_duration = f" {asset_name} 15 minute"

    is_usual = is_bitcoin and is_5m
    alert_header = "⚡ FARKLI İŞLEM ⚡\n" if not is_usual else ""
    if not is_usual:
        emoji = "⚡" + emoji

    name_display = f"{nickname}" if nickname else f"{wallet[:6]}..."
    
    timestamp = trade.get("timestamp", "")
    time_str = ""
    if timestamp:
        try:
            ts = float(timestamp)
            if ts > 1e11:
                ts /= 1000
            time_str = datetime.fromtimestamp(ts).strftime("%b %d, %I:%M %p")
        except:
            time_str = str(timestamp)
            
    # Remove newline from display_title if it exists
    display_title = display_title.replace("\n", " | ")
    
    # 1. Line: Alert Header (if any)
    # 2. Line: Amount | Outcome Market | Price
    msg = f"{alert_header}{emoji} {total_spent:.2f}$ | {outcome.upper()}{market_duration} | 💰 {price:.3f}$\n"
    # 3. Line: Title
    msg += f"📊 {display_title}\n"
    # 4. Line: Whale Name and System Time
    msg += f"👤 {name_display}"
    if time_str:
        msg += f" | ⏰ {time_str}"
        
    return msg

async def fetch_recent_trades(session: aiohttp.ClientSession, address: str):
    params = {
        "user": address, 
        "limit": 15,  # Reduced from 50 - we only care about recent trades
        "_": int(time.time() * 1000)
    }
    try:
        async with session.get(POLYMARKET_API_URL, params=params) as response:
            if response.status == 200:
                data = await response.json()
                trades = [item for item in data if item.get("type") == "TRADE"]
                return trades
            else:
                logger.error(f"API returned {response.status} for {address}")
                return None
    except Exception as e:
        logger.error(f"Fetch error for {address}: {e}")
        return None

async def process_wallet(session: aiohttp.ClientSession, whale: dict):
    address = whale['address']
    nickname = whale.get('name')
    
    trades = await fetch_recent_trades(session, address)
    if not trades:
        return
    
    # FAST PATH: Check against in-memory cache (no DB calls!)
    new_trades = []
    for trade in trades:
        tx_hash = trade.get("transactionHash")
        if not tx_hash:
            continue
        if is_activity_seen_fast(address, tx_hash):
            break
        new_trades.append(trade)
        
    if not new_trades:
        return
        
    logger.info(f"⚡ {len(new_trades)} new trades for {nickname} ({address[:6]}...)")
    
    # Collect DB records for batch write
    db_records = []
    
    for trade in reversed(new_trades):
        try:
            tx_hash = trade.get("transactionHash")
            title = str(trade.get("title") or "")
            
            # CRYPTO FILTER: Spor betlerini atla, sadece crypto market'leri bildir
            if not is_crypto_market(title):
                logger.info(f"🚫 SPOR/DİĞER BET FİLTRELENDİ: {title} ({nickname})")
                # Yine de seen olarak işaretle ki tekrar işlenmesin
                mark_activity_seen_fast(address, tx_hash)
                db_records.append((address, tx_hash, trade.get("timestamp")))
                continue
            
            msg = format_telegram_message(address, trade, nickname)
            await send_notification(msg, chat_id=whale.get('chat_id'))
            # Mark in RAM immediately (prevents duplicates in next poll)
            mark_activity_seen_fast(address, tx_hash)
            db_records.append((address, tx_hash, trade.get("timestamp")))
        except Exception as e:
            logger.error(f"Error processing trade {tx_hash}: {e}")
    
    # Single batch DB write instead of one per trade
    await batch_record_activities(db_records)

async def tracker_loop():
    logger.info("Tracker loop started")
    
    # Load all seen tx hashes into RAM at startup
    count = await load_seen_cache()
    logger.info(f"📦 Loaded {count} seen tx hashes into memory cache")
    
    connector = aiohttp.TCPConnector(limit=50, enable_cleanup_closed=True)
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout, headers=HEADERS) as session:
        # --- STARTUP CHECK ---
        try:
            whales = await get_whales_cached()
            active_whales = [w for w in whales if w.get('status', 'tracking') == 'tracking']
            if active_whales:
                first_whale = active_whales[0]
                trades = await fetch_recent_trades(session, first_whale['address'])
                if trades and len(trades) > 0:
                    last_trade = trades[0]
                    msg = format_telegram_message(first_whale['address'], last_trade, first_whale.get('name'))
                    await send_notification(f"✅ <b>SİSTEM BAŞARIYLA BAŞLATILDI!</b>\n🐋 {len(active_whales)} balina takipte\n📦 {count} kayıtlı işlem hafızada\n⏱ Tarama aralığı: {POLL_INTERVAL}s\n\nSon işlem:\n{msg}")
                else:
                    await send_notification(f"✅ <b>SİSTEM BAŞARIYLA BAŞLATILDI!</b>\n🐋 {len(active_whales)} balina takipte\nBağlantı başarılı ancak geçmiş işlem bulunamadı.")
            else:
                await send_notification("✅ <b>SİSTEM BAŞARIYLA BAŞLATILDI!</b>\nLütfen takip için aktif bir cüzdan adresi ekleyin.")
        except Exception as e:
            logger.error(f"Startup check failed: {e}")
            await send_notification(f"⚠️ <b>SİSTEM BAŞLATILDI ANCAK API BAĞLANTISINDA SORUN VAR!</b>\n{e}")
        # ---------------------
        
        while True:
            try:
                whales = await get_whales_cached()
                active_whales = [w for w in whales if w.get('status', 'tracking') == 'tracking']
                if not active_whales:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                tasks = [process_wallet(session, whale) for whale in active_whales]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                await asyncio.sleep(POLL_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Tracker loop error: {e}")
                await asyncio.sleep(POLL_INTERVAL)
