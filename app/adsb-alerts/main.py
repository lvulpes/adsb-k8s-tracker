import asyncio
import json
import logging
import os

import asyncpg

DB_DSN = os.getenv("DB_DSN", "postgresql://postgres:password@adsb-db:5432/adsb")
SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", "60"))
CONFIG_PATH = os.getenv("FILTER_PATH", '/app/adsb-alerts/filters.json')
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logging.info(f"Logger initialized at level: {LOG_LEVEL}")

def read_filters(file_path: str) -> list[str]:
    """Reads mounted ConfigMap from disk."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

async def fetch_last_aircraft(pool, max_age_seconds: int) -> list:
    query = """
        SELECT *
        FROM aircraft
        WHERE last_updated >= NOW() - ($1 || ' seconds')::interval
    """
    
    async with pool.acquire() as conn:
        return await conn.fetch(query, max_age_seconds)

async def filter_aircraft(ac: dict, ac_filter: dict) -> dict:
    for k in ac_filter.keys():
        if k in ac.keys():
            # We found one matching filter name
            logging.debug(f"Found matching key {k} on aircraft {ac['hex']}")
            if ac_filter[k] == ac[k]:
                # We found a match on this specific filter parameter, but need to check ALL
                logging.debug(f"Found match for {k}: {ac[k]} == {ac_filter[k]}")
                continue
            else:
                # No match, stop looking
                return {}
    # If we reach the end it means we had a match on all filter parameters
    return ac

async def main():
    # Setup async DB pool once
    db_pool = await asyncpg.create_pool(dsn=DB_DSN)
    
    try:
        while True:
            # 1. Non-blocking ConfigMap read (via thread)
            ac_filter_list = await asyncio.to_thread(read_filters, CONFIG_PATH)

            # 2. Non-blocking DB query
            new_aircraft = await fetch_last_aircraft(db_pool, SLEEP_INTERVAL)

            # 3. Process results
            for ac in new_aircraft:
                logging.debug(f"Checking filter for ac {ac['hex']}")
                # Check all filters for each aircraft
                for f_name, f_conf in ac_filters.items():
                    matching_ac = filter_aircraft(ac, f_conf)
                    if matching_ac:
                        logging.info(f"Found match for aircraft {ac['hex']} in filter {f_name}")
                        
            logging.info(f"Found match for aircraft {ac['hex']}")
            await asyncio.sleep(SLEEP_INTERVAL)
    finally:
        await db_pool.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
