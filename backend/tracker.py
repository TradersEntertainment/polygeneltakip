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
    side = trade.get("side", "UNKNOWN").upper()
    size = float(trade.get("size", 0))
    price = float(trade.get("price", 0))
    title = trade.get("title", "Unknown Market")
    outcome = trade.get("outcome", "Unknown Outcome")
    
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
                            market_duration = f" {int(diff)} minute market"
                    except:
                        pass
                        
            display_title += f"\n⏰ {time_part}"

    if not market_duration:
        if "5-minute" in title.lower() or "5 minute" in title.lower():
            market_duration = " 5 minute market"
        elif "15-minute" in title.lower() or "15 minute" in title.lower():
            market_duration = " 15 minute market"
            
    name_display = f"Balina adı : {nickname}" if nickname else f"Balina: {wallet}"
    
    timestamp = trade.get("timestamp", "")
    time_str = ""
    if timestamp:
        try:
            ts = float(timestamp)
            if ts > 1e11:
                ts /= 1000
            time_str = datetime.fromtimestamp(ts).strftime("%B %d, %I:%M %p ET")
        except:
            time_str = str(timestamp)
            
    msg = f"{emoji} {total_spent:.2f}$ | {outcome}{market_duration}\n"
    msg += f"💰 Fiyat: {price:.3f}$\n"
    msg += f"📊 {display_title}\n"
    if time_str:
        msg += f"⏰ {time_str}\n"
    msg += f"{name_display}\n"
    
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
