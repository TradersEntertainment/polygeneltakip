import aiosqlite
import os

DB_PATH = "data/balina.db"

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
