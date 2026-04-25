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
    
    total_spent = round(size * price, 2)
    
    if outcome.lower() == "up":
        emoji = "🟢"
    elif outcome.lower() == "down":
        emoji = "🔴"
    else:
        emoji = "🔵"
        
    display_title = title
    if " - " in title:
        parts = title.split(" - ")
        if len(parts) > 1:
            display_title = f"{parts[0]}\n⏰ {parts[1]}"
            
    name_display = f"Balina adı : {nickname}" if nickname else f"Balina: {wallet}"
    
    # 🔴 5.00$ | Down 5 minute market
    # 📊 Bitcoin Up or Down - April 20, 5:25AM-5:30AM ET
    # ⏰ January 21, 8:31 AM ET
    # 💰 Fiyat: 0.660$
    # Balina adı :  150dollarsto10k
    
    timestamp = trade.get("timestamp", "")
    
    msg = f"{emoji} {total_spent}$ | {outcome} {side} market\n"
    msg += f"📊 {display_title}\n"
    if timestamp:
        msg += f"⏰ {timestamp}\n"
    msg += f"💰 Fiyat: {price:.3f}$\n"
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
