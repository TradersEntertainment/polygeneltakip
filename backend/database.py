import aiosqlite
import os

DB_PATH = "data/balina.db"

INITIAL_WHALES = [
    ("0x4c353dd347c2e7d8bcdc5cd6ee569de7baf23e2f", "wangxingyu", None),
    ("0x6075106cd4f0155a68a0eb4cfd3b78f241aa3a62", "lutnicksniper", "-1003965316610"),
    ("0x01ca5c77bf032f10b7cb5e3f730fbf497523200d", "takipşüpheli", None),
    ("0x9ac833e9cf85bb662cd4a0cfe3b3b4df7222d27c", "GGFAFSGH874", "-5050772123"),
    ("0x841026ac0ddaa67d42e8075f2979cf7ba284228c", "yenibalina wkknndoqmz", None),
    ("0x725fd0798eca95357696f2521dd1d4784162570c", "5limafya", None),
    ("0x7543dad3d9b2f6cb8d86e2f9c385a03c4df68147", "5limafya2", "-5297283951"),
    ("0xa0a5078359dad63993a868f6d2db82d3a7b3606f", "saatçi", "-5237484521"),
    ("0xeefe46deee8da83bf67dc95b6bc8b8f73e77be43", "satıcıbalina", "-5297283951"),
    ("0x780cdebc22dd4d3cfadd3882d71c216d544b3b11", "jhwjknmmql", "-5011899341"),
    ("0x44e564c21530fa397591da137bccabaaedeefdbe", "jeidfhfqqz", "-5011899341"),
    ("0x51ef3e5e7d5a3151c7caf165079270dbe905cda1", "ndjjwobaq", "-5011899341"),
    ("0x9dae874a2e804349e3004ccc98107799f15f97a2", "Prgovindu1", "-5050772123"),
    ("0x7f59998477864871448e312011fa5cc6b210b636", "Unusal-Orange", None),
    ("0x3e6bfd2f791a10cf2404e09542c2a82e3e7b6d63", "btcbeliever", "-5289733229"),
    ("0xe9ba96828e513a6cc35fb196297716f558e2f626", "80lerrdanbilealıyor", "-5198649776"),
    ("0x823d73ef41bb2570ee7fbcd5a97d73216ea40dba", "yepyenibalina", "-5124053137"),
    ("0x5532c66fa9fbdc89b136e7e8c42e76fe18953f46", "unusalorangeyenihesap", None),
    ("0xbadb9af986ee66437bd39e6cd3d3036cbbdc31a7", "damarlibalina", "-5124053137"),
    ("0x8d2d7bae900cc62bbac531f900dbf58a6f8c5517", "1.adam", "-5149193503"),
    ("0x76955f60d665ecfae7480c127a5e6f87d69f9ced", "2.adam", "-5149193503"),
    ("0x65d887fcfb195022ddc1084b8063027300e6b2dd", "3.adam", "-5149193503"),
    ("0x18614c6c85500f0ff39e4faa77ff62f427e4ff2a", "nnnnnn1111", "-5297283951"),
    ("0x34A9e26Af9bcEc22A27CBc96F55CDbb39aD74CFD", "canavarbalina", "-5255654506"),
    ("0xb3fdfe2e3d04f31e5b54a908f928e25511e322c7", "4.adam", "-5149193503")
]

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS whales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'tracking'
            )
        """)
        try:
            await db.execute("ALTER TABLE whales ADD COLUMN chat_id TEXT")
        except aiosqlite.OperationalError:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_history (
                address TEXT NOT NULL,
                tx_hash TEXT NOT NULL,
                timestamp TEXT,
                PRIMARY KEY (address, tx_hash)
            )
        """)
        
        # Insert hardcoded whales with chat IDs
        for address, name, chat_id in INITIAL_WHALES:
            await db.execute(
                "INSERT OR IGNORE INTO whales (address, name, chat_id) VALUES (?, ?, ?)", 
                (address, name, chat_id)
            )
            
        await db.commit()

async def get_whales():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM whales") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def add_whale(address: str, name: str, chat_id: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO whales (address, name, chat_id) VALUES (?, ?, ?)", (address, name, chat_id))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False # Already exists

async def remove_whale(address: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM whales WHERE address = ?", (address,))
        await db.commit()
        return True

async def is_activity_seen(address: str, tx_hash: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM activity_history WHERE address = ? AND tx_hash = ?", (address, tx_hash)) as cursor:
            return await cursor.fetchone() is not None

async def record_activity(address: str, tx_hash: str, timestamp: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO activity_history (address, tx_hash, timestamp) VALUES (?, ?, ?)", (address, tx_hash, timestamp))
        await db.commit()

# ============================================================
# IN-MEMORY CACHE LAYER - eliminates per-trade DB round-trips
# ============================================================
import time as _time

# Global in-memory set of "(address, tx_hash)" pairs
_seen_cache: set = set()
_seen_cache_loaded: bool = False

# Whale list cache
_whales_cache: list = []
_whales_cache_ts: float = 0
_WHALES_CACHE_TTL = 30  # refresh whale list from DB every 30 seconds

async def load_seen_cache():
    """Load all seen tx hashes into memory at startup. Call once."""
    global _seen_cache, _seen_cache_loaded
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT address, tx_hash FROM activity_history") as cursor:
            rows = await cursor.fetchall()
            _seen_cache = {(row[0], row[1]) for row in rows}
    _seen_cache_loaded = True
    return len(_seen_cache)

def is_activity_seen_fast(address: str, tx_hash: str) -> bool:
    """Check seen status from RAM - instant, no DB call."""
    return (address, tx_hash) in _seen_cache

def mark_activity_seen_fast(address: str, tx_hash: str):
    """Mark as seen in RAM immediately (DB write happens in batch)."""
    _seen_cache.add((address, tx_hash))

async def batch_record_activities(records: list):
    """Write multiple (address, tx_hash, timestamp) in one DB transaction."""
    if not records:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT OR IGNORE INTO activity_history (address, tx_hash, timestamp) VALUES (?, ?, ?)",
            records
        )
        await db.commit()

async def get_whales_cached():
    """Return whale list from cache, refresh from DB every 30 seconds."""
    global _whales_cache, _whales_cache_ts
    now = _time.time()
    if not _whales_cache or (now - _whales_cache_ts) > _WHALES_CACHE_TTL:
        _whales_cache = await get_whales()
        _whales_cache_ts = now
    return _whales_cache

def invalidate_whales_cache():
    """Call after add/remove whale to force refresh."""
    global _whales_cache_ts
    _whales_cache_ts = 0
