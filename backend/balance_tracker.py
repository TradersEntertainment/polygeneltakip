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

# Polygon RPC URLs (stable public endpoints with fallback support)
POLYGON_RPCS = [
    os.getenv("POLYGON_RPC_URL", "https://polygon-bor-rpc.publicnode.com"),
    "https://1rpc.io/matic",
    "https://polygon.llamarpc.com",
    "https://polygon-rpc.com"
]

# pUSD (Polymarket USD) contract on Polygon (Polymarket uses this for account balances)
USDC_CONTRACT = "0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb"

# Polymarket Data API
POLYMARKET_VALUE_URL = "https://data-api.polymarket.com/value"

# How often to check balances (seconds) - less frequent than trade tracking
BALANCE_CHECK_INTERVAL = 60  # every 60 seconds

# Bakiye $1000 altına düşünce bildirim gönder
LOW_BALANCE_THRESHOLD = 1000  # $1000

# Dedicated Telegram chat/channel ID for all balance-related alerts (deposits/low balances)
BALANCE_ALERTS_CHAT_ID = os.getenv("BALANCE_ALERTS_CHAT_ID", "-5251294356")

# In-memory cache: address -> {usdc_balance, portfolio_value, last_updated, low_balance_notified}
_balance_cache: dict = {}


async def fetch_usdc_balance(session: aiohttp.ClientSession, address: str) -> float:
    """Fetch pUSD (Polymarket USD) balance from Polygon chain via RPC with fallbacks and JSON-RPC error protection."""
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
    
    # Try multiple RPCs to ensure reliability
    for rpc_url in POLYGON_RPCS:
        try:
            async with session.post(rpc_url, json=payload, timeout=5) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    # Check for JSON-RPC error or missing result field
                    if "error" in result or "result" not in result:
                        logger.warning(f"⚠️ RPC {rpc_url} returned JSON-RPC error or missing result field for {address}: {result.get('error')}")
                        continue
                        
                    hex_balance = result.get("result")
                    if hex_balance is None or hex_balance == "0x":
                        logger.warning(f"⚠️ RPC {rpc_url} returned empty hex balance for {address}")
                        continue
                        
                    # pUSD has 6 decimals
                    balance = int(hex_balance, 16) / 1e6
                    return balance
                else:
                    logger.warning(f"⚠️ RPC {rpc_url} returned status {response.status} for {address}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch balance from RPC {rpc_url} for {address}: {e}")
            
    logger.error(f"❌ All Polygon RPCs failed to fetch balance for {address}")
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
    """Check a single whale's balance. Only notify when balance drops below $1000 and stays there for 10 mins."""
    address = whale['address']
    nickname = whale.get('name', address[:8])
    
    # Fetch both balances concurrently
    usdc_balance, portfolio_value = await asyncio.gather(
        fetch_usdc_balance(session, address),
        fetch_portfolio_value(session, address)
    )
    
    if usdc_balance < 0:
        # RPC query failed. Do NOT trust or update USDC balance to 0 to prevent fake alerts!
        logger.warning(f"⚠️ Polygon RPC failed for {nickname} ({address}). Balance check skipped to prevent fake alerts.")
        return
        
    if portfolio_value < 0:
        portfolio_value = 0  # Treat portfolio value fetch failure gracefully as 0 without blocking USDC
    
    now = time.time()
    
    # Get previous state from cache
    prev = _balance_cache.get(address)
    was_notified = prev.get("low_balance_notified", False) if prev else False
    low_balance_started_at = prev.get("low_balance_started_at", None) if prev else None
    
    # Track low balance start time
    if usdc_balance < LOW_BALANCE_THRESHOLD:
        if low_balance_started_at is None:
            low_balance_started_at = now
    else:
        low_balance_started_at = None
        was_notified = False
        
    # Update cache
    _balance_cache[address] = {
        "usdc_balance": max(usdc_balance, 0),
        "portfolio_value": max(portfolio_value, 0),
        "last_updated": now,
        "nickname": nickname,
        "low_balance_notified": was_notified,
        "low_balance_started_at": low_balance_started_at
    }
    
    # If first time, just record (no notification)
    if prev is None:
        logger.info(f"💰 İlk bakiye kaydı: {nickname} | USDC: ${usdc_balance:.2f} | Portfolio: ${portfolio_value:.2f}")
        return
    
    prev_usdc = prev.get("usdc_balance", 0)
    prev_portfolio = prev.get("portfolio_value", 0)
    prev_total = prev_usdc + prev_portfolio
    current_total = usdc_balance + portfolio_value
    
    # 💰 PARA YATIRMA TESPİTİ: 
    # Düşük bakiyeli (USDC < 1000) bir balina hesaba yeni para yatırırsa ve toplam değeri (USDC + Portfolio) $3000'ı geçerse bildir
    if (
        prev_usdc < LOW_BALANCE_THRESHOLD and
        usdc_balance > prev_usdc and
        current_total >= 3000 and
        prev_total < 3000 and
        whale.get('status', 'tracking') == 'tracking'
    ):
        _balance_cache[address]["low_balance_notified"] = False  # Reset low balance flag immediately
        _balance_cache[address]["low_balance_started_at"] = None
        msg = (
            f"💰 <b>YENİ PARA YATIRMA TESPİT EDİLDİ!</b>\n"
            f"👤 {nickname}\n"
            f"💸 USDC: ${prev_usdc:,.2f} → <b>${usdc_balance:,.2f}</b>\n"
            f"🎯 Portfolio: ${portfolio_value:,.2f}\n"
            f"✨ Toplam Değer: <b>${current_total:,.2f}</b> (USDC + Portfolio)\n"
            f"✅ Balina hesaba yeni fon yatırdı!"
        )
        await send_notification(msg, chat_id=BALANCE_ALERTS_CHAT_ID)
        logger.info(f"💰 Deposit detected: {nickname} USDC={usdc_balance:.2f} Total={current_total:.2f}")

    # SADECE bakiye $1000 altına düşüp en az 10 dakika (600 saniye) boyunca düşük kalırsa bildir
    LOW_BALANCE_DURATION = 600  # 10 minutes delay to prevent fake alerts
    if usdc_balance < LOW_BALANCE_THRESHOLD and whale.get('status', 'tracking') == 'tracking':
        if low_balance_started_at is not None:
            elapsed = now - low_balance_started_at
            if elapsed >= LOW_BALANCE_DURATION and not was_notified:
                _balance_cache[address]["low_balance_notified"] = True
                msg = (
                    f"🚨 <b>BAKİYE ${LOW_BALANCE_THRESHOLD:,} ALTINDA (10 Dk. Süresince)!</b>\n"
                    f"👤 {nickname}\n"
                    f"💸 Önceki: ${prev_usdc:,.2f} → Şimdi: <b>${usdc_balance:,.2f}</b>\n"
                    f"🎯 Portfolio: ${portfolio_value:,.2f}\n"
                    f"⚠️ Balina bakiyesi 10 dakikadır düşük seviyede kalmaya devam ediyor!"
                )
                await send_notification(msg, chat_id=BALANCE_ALERTS_CHAT_ID)
                logger.info(f"🚨 Low balance alert (delayed 10m): {nickname} USDC=${usdc_balance:.2f}")
    
    # Bakiye tekrar $1000 üstüne çıkarsa flag'leri resetle (bir sonraki düşüşte tekrar bildirilsin)
    if usdc_balance >= LOW_BALANCE_THRESHOLD and was_notified:
        _balance_cache[address]["low_balance_notified"] = False
        _balance_cache[address]["low_balance_started_at"] = None
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
