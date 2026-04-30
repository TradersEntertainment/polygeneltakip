import asyncio
import time
import aiohttp
import logging
from database import get_whales, is_activity_seen, record_activity
from bot_engine import send_notification

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

POLYMARKET_API_URL = "https://data-api.polymarket.com/activity"
POLL_INTERVAL = 10

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
        "limit": 10,
        "_": int(time.time() * 1000)
    }
    try:
        async with session.get(POLYMARKET_API_URL, params=params) as response:
            if response.status == 200:
                data = await response.json()
                trades = [item for item in data if item.get("type") == "TRADE"]
                return trades
            else:
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
        
    new_trades = []
    for trade in trades:
        tx_hash = trade.get("transactionHash")
        if not tx_hash:
            continue
        if await is_activity_seen(address, tx_hash):
            break
        new_trades.append(trade)
        
    if not new_trades:
        return
        
    logger.info(f"⚡ {len(new_trades)} new trades for {nickname} ({address[:6]}...)")
    
    for trade in reversed(new_trades):
        try:
            tx_hash = trade.get("transactionHash")
            msg = format_telegram_message(address, trade, nickname)
            await send_notification(msg)
            await record_activity(address, tx_hash, trade.get("timestamp"))
        except Exception as e:
            logger.error(f"Error processing trade {tx_hash}: {e}")

async def tracker_loop():
    logger.info("Tracker loop started")
    connector = aiohttp.TCPConnector(limit=10, enable_cleanup_closed=True)
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout, headers=HEADERS) as session:
        while True:
            try:
                whales = await get_whales()
                if not whales:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                tasks = [process_wallet(session, whale) for whale in whales]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                await asyncio.sleep(POLL_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Tracker loop error: {e}")
                await asyncio.sleep(POLL_INTERVAL)
