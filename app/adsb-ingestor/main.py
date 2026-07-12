import asyncio
import aiohttp
import asyncpg
import os
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import uvicorn

# K8s environment variables
DB_DSN = os.getenv("DB_DSN", "postgresql://postgres:password@adsb-db:5432/adsb")
DECODER_URL = os.getenv("DECODER_URL", "http://adsb-decoder/data/aircraft.json")
API_URL = os.getenv("API_URL", "http://adsb-api/api/aircraft")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LISTEN_PORT = os.getenv("LISTEN_PORT", "8000")

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logging.info(f"Logger initialized at level: {LOG_LEVEL}")

# Global references for the app lifespan
db_pool = None
http_session = None

async def init_db(pool):
    """Sets up the Postgres tables if they don't exist, linking position to aircraft."""
    async with pool.acquire() as conn:
        logging.info("Initializing database schema...")
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS aircraft (
                hex VARCHAR(10) PRIMARY KEY,
                flight VARCHAR(20),
                registration VARCHAR(20),
                type_code VARCHAR(10),
                description TEXT,
                operator TEXT,
                category VARCHAR(10),
                filter VARCHAR(30),
                last_updated TIMESTAMPTZ DEFAULT NOW()
            );
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS position (
                id SERIAL PRIMARY KEY,
                hex VARCHAR(10) REFERENCES aircraft(hex) ON DELETE CASCADE,
                lat DOUBLE PRECISION,
                lon DOUBLE PRECISION,
                alt_baro INTEGER,
                alt_geom INTEGER,
                gs DOUBLE PRECISION,
                track DOUBLE PRECISION,
                squawk VARCHAR(10),
                timestamp TIMESTAMPTZ DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_position_hex_time ON position(hex, timestamp DESC);
        ''')
        logging.info("Database schema ready.")

async def upsert_aircraft_data(pool, aircraft_list, source):
    """Inserts or updates aircraft and appends new positions."""
    if not aircraft_list:
        return

    async with pool.acquire() as conn:
        async with conn.transaction():
            for ac in aircraft_list:
                hex_code = ac.get("hex")
                if not hex_code:
                    continue

                await conn.execute('''
                    INSERT INTO aircraft (hex, flight, registration, type_code, description, operator, category, filter, last_updated)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                    ON CONFLICT (hex) DO UPDATE SET
                        flight = COALESCE(EXCLUDED.flight, aircraft.flight),
                        registration = COALESCE(EXCLUDED.registration, aircraft.registration),
                        type_code = COALESCE(EXCLUDED.type_code, aircraft.type_code),
                        description = COALESCE(EXCLUDED.description, aircraft.description),
                        operator = COALESCE(EXCLUDED.operator, aircraft.operator),
                        category = COALESCE(EXCLUDED.category, aircraft.category),
                        filter = COALESCE(EXCLUDED.filter, aircraft.filter),
                        last_updated = NOW();
                ''', 
                hex_code, ac.get("flight", "").strip() if ac.get("flight") else None, 
                ac.get("r"), ac.get("t"), ac.get("desc"), ac.get("ownOp"), ac.get("category"),
                ac.get("filter"))

                if ac.get("lat") is not None and ac.get("lon") is not None:
                    await conn.execute('''
                        INSERT INTO position (hex, lat, lon, alt_baro, alt_geom, gs, track, squawk)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ''', 
                    hex_code, ac.get("lat"), ac.get("lon"), ac.get("alt_baro"),
                    ac.get("alt_geom"), ac.get("gs"), ac.get("track"), ac.get("squawk"))

    logging.info(f"Processed {len(aircraft_list)} records from {source}")

async def fetch_decoder_data(session, url, pool):
    """Polls the local decoder JSON endpoint and triggers the DB upsert."""
    while True:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    aircraft_list = data.get("aircraft", data) if isinstance(data, dict) else data
                    await upsert_aircraft_data(pool, aircraft_list, "adsb-decoder")
                else:
                    logging.warning(f"adsb-decoder returned status {response.status}")
        except Exception as e:
            logging.error(f"Error fetching from adsb-decoder at {url}: {e}")
        
        await asyncio.sleep(POLL_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages the startup and shutdown sequence."""
    global db_pool, http_session
    logging.info("Starting adsb-ingestor...")
    
    # 1. Setup DB
    db_pool = await asyncpg.create_pool(dsn=DB_DSN)
    await init_db(db_pool)
    
    # 2. Setup HTTP session for polling
    http_session = aiohttp.ClientSession()
    
    # 3. Start background polling task for the local decoder
    # decoder_task = asyncio.create_task(fetch_decoder_data(http_session, DECODER_URL, db_pool))
    
    yield # App is running and receiving POST requests
    
    # 4. Teardown
    # decoder_task.cancel()
    await http_session.close()
    await db_pool.close()

app = FastAPI(lifespan=lifespan)

@app.post("/api/v1/enrich")
async def receive_api_data(request: Request):
    """Endpoint for adsb-api to push data via HTTP POST."""
    try:
        data = await request.json()
        aircraft_list = data.get("aircraft", data) if isinstance(data, dict) else data
        
        # Ensure it's a list before processing to avoid errors
        if isinstance(aircraft_list, list):
            await upsert_aircraft_data(db_pool, aircraft_list, "adsb-api (HTTP POST)")
            return {"status": "success", "processed": len(aircraft_list)}
        else:
            return {"status": "error", "message": "Payload format invalid. Expected a list or dict with 'aircraft' array."}, 400
            
    except Exception as e:
        logging.error(f"Error processing POST data: {e}")
        return {"status": "error", "message": str(e)}, 500

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT)
