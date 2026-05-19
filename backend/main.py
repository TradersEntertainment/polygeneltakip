import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import init_db, get_whales, add_whale, remove_whale, invalidate_whales_cache
from tracker import tracker_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Startup and shutdown tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up application...")
    # Initialize Database
    await init_db()
    
    # Start the tracker loop in the background
    tracker_task = asyncio.create_task(tracker_loop())
    
    yield
    
    # Clean up on shutdown
    logger.info("Shutting down application...")
    tracker_task.cancel()
    try:
        await tracker_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="Poly Whale Tracker API", lifespan=lifespan)

# Allow CORS for dashboard UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for demo, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from typing import Optional

class WhaleCreate(BaseModel):
    address: str
    name: str
    chat_id: Optional[str] = None

@app.get("/api/whales")
async def api_get_whales():
    try:
        whales = await get_whales()
        return {"whales": whales}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/whales")
async def api_add_whale(whale: WhaleCreate):
    try:
        success = await add_whale(whale.address, whale.name, whale.chat_id)
        if success:
            invalidate_whales_cache()
            return {"success": True, "message": "Whale added successfully"}
        else:
            raise HTTPException(status_code=400, detail="Whale already exists")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/whales/{address}")
async def api_remove_whale(address: str):
    try:
        success = await remove_whale(address)
        invalidate_whales_cache()
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
