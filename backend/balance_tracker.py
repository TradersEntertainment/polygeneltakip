import asyncio
import time
import aiohttp
import logging
import os
from bot_engine import send_notification
from database import get_whales_cached

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# BALANCE TRACKER - Balina hesap bakiyelerini takip et
# USDC balance (Polygon on-chain) + Portfolio value (Polymarket)
# Bakiye değişikliklerinde Telegram bildirimi gönder
# ============================================================

# Polygon RPC (public endpoint, can be replaced with private one)
POLYGON_RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")

# USDC.e contract on Polygon (Polymarket uses this)
USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# Polymarket Data API
POLYMARKET_VALUE_URL = "https://data-api.polymarket.com/value"

# How often to check balances (seconds) - less frequent than trade tracking
BALANCE_CHECK_INTERVAL = 60  # every 60 seconds

# Bakiye $1000 altına düşünce bildirim gönder
LOW_BALANCE_THRESHOLD = 1000  # $1000

# In-memory cache: address -> {usdc_balance, portfolio_value, last_updated, low_balance_notified}
_balance_cache: dict = {}


async def fetch_usdc_balance(session: aiohttp.ClientSession, address: str) -> float:
    """Fetch USDC balance from Polygon chain via RPC."""
    # balanceOf(address) function selector: 0x70a08231
    # Pad address to 32 bytes
    clean_address = address.lower().replace("0x", "").zfill(64)
    data = f"0x70a08231{clean_address}"
    
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [
            {
                "to": USDC_CONTRACT,
                "data": data
            },
            "latest"
        ],
        "id": 1
    }
    
    try:
        async with session.post(POLYGON_RPC_URL, json=payload) as response:
            if response.status == 200:
                result = await response.json()
                hex_balance = result.get("result", "0x0")
                # USDC has 6 decimals
                balance = int(hex_balance, 16) / 1e6
                return balance
            else:
                logger.error(f"RPC error {response.status} for {address}")
                return -1
    except Exception as e:
        logger.error(f"USDC balance fetch error for {address}: {e}")
        return -1


async def fetch_portfolio_value(session: aiohttp.ClientSession, address: str) -> float:
    """Fetch portfolio value from Polymarket Data API."""
    params = {
        "user": address,
        "_": int(time.time() * 1000)
    }
    
    try:
        async with session.get(POLYMARKET_VALUE_URL, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data and len(data) > 0:
                    return float(data[0].get("value", 0))
                return 0
            else:
                logger.error(f"Portfolio API error {response.status} for {address}")
                return -1
    except Exception as e:
        logger.error(f"Portfolio value fetch error for {address}: {e}")
        return -1


async def check_whale_balance(session: aiohttp.ClientSession, whale: dict):
    """Check a single whale's balance. Only notify when balance drops below $1000."""
    address = whale['address']
    nickname = whale.get('name', address[:8])
    
    # Fetch both balances concurrently
    usdc_balance, portfolio_value = await asyncio.gather(
        fetch_usdc_balance(session, address),
        fetch_portfolio_value(session, address)
    )
    
    if usdc_balance < 0 and portfolio_value < 0:
        return  # Both failed, skip
    
    now = time.time()
    
    # Get previous state from cache
    prev = _balance_cache.get(address)
    was_notified = prev.get("low_balance_notified", False) if prev else False
    
    # Update cache
    _balance_cache[address] = {
        "usdc_balance": max(usdc_balance, 0),
        "portfolio_value": max(portfolio_value, 0),
        "last_updated": now,
        "nickname": nickname,
        "low_balance_notified": was_notified
    }
    
    # If first time, just record (no notification)
    if prev is None:
        # İlk kayıtta da $1000 altındaysa bildir
        if usdc_balance >= 0 and usdc_balance < LOW_BALANCE_THRESHOLD:
            _balance_cache[address]["low_balance_notified"] = True
            msg = (
                f"🚨 <b>DÜŞÜK BAKİYE TESPİT EDİLDİ</b>\n"
                f"👤 {nickname}\n"
                f"💰 USDC: <b>${usdc_balance:,.2f}</b>\n"
                f"🎯 Portfolio: ${portfolio_value:,.2f}\n"
                f"⚠️ Bakiye ${LOW_BALANCE_THRESHOLD:,} altında!"
            )
            await send_notification(msg, chat_id=whale.get('chat_id'))
        logger.info(f"💰 İlk bakiye kaydı: {nickname} | USDC: ${usdc_balance:.2f} | Portfolio: ${portfolio_value:.2f}")
        return
    
    prev_usdc = prev.get("usdc_balance", 0)
    
    # SADECE bakiye $1000 altına düşünce bildir (ve daha önce bildirilmemişse)
    if usdc_balance >= 0 and usdc_balance < LOW_BALANCE_THRESHOLD and not was_notified:
        _balance_cache[address]["low_balance_notified"] = True
        msg = (
            f"🚨 <b>BAKİYE ${LOW_BALANCE_THRESHOLD:,} ALTINA DÜŞTÜ!</b>\n"
            f"👤 {nickname}\n"
            f"💸 Önceki: ${prev_usdc:,.2f} → Şimdi: <b>${usdc_balance:,.2f}</b>\n"
            f"🎯 Portfolio: ${portfolio_value:,.2f}\n"
            f"⚠️ Balina parayı çekmiş olabilir!"
        )
        await send_notification(msg, chat_id=whale.get('chat_id'))
        logger.info(f"🚨 Low balance alert: {nickname} USDC=${usdc_balance:.2f}")
    
    # Bakiye tekrar $1000 üstüne çıkarsa flag'i resetle (bir sonraki düşüşte tekrar bildirilsin)
    if usdc_balance >= LOW_BALANCE_THRESHOLD and was_notified:
        _balance_cache[address]["low_balance_notified"] = False
        logger.info(f"✅ Balance recovered: {nickname} USDC=${usdc_balance:.2f}")


def get_all_balances() -> dict:
    """Return cached balances for all whales (for API endpoint)."""
    return {
        address: {
            "usdc_balance": info.get("usdc_balance", 0),
            "portfolio_value": info.get("portfolio_value", 0),
            "last_updated": info.get("last_updated", 0),
            "nickname": info.get("nickname", "")
        }
        for address, info in _balance_cache.items()
    }


async def balance_tracker_loop():
    """Main loop that periodically checks all whale balances."""
    logger.info("💰 Balance tracker loop started")
    
    connector = aiohttp.TCPConnector(limit=20, enable_cleanup_closed=True)
    timeout = aiohttp.ClientTimeout(total=15)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout, headers=headers) as session:
        while True:
            try:
                whales = await get_whales_cached()
                if not whales:
                    await asyncio.sleep(BALANCE_CHECK_INTERVAL)
                    continue
                
                # Check balances in small batches to avoid rate limits
                batch_size = 5
                for i in range(0, len(whales), batch_size):
                    batch = whales[i:i + batch_size]
                    tasks = [check_whale_balance(session, whale) for whale in batch]
                    await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Small delay between batches to be nice to RPC
                    if i + batch_size < len(whales):
                        await asyncio.sleep(2)
                
                logger.info(f"💰 Balance check complete for {len(whales)} whales")
                await asyncio.sleep(BALANCE_CHECK_INTERVAL)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Balance tracker loop error: {e}")
                await asyncio.sleep(BALANCE_CHECK_INTERVAL)
