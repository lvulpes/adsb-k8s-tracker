import asyncio
from datetime import datetime, timezone
import json
import logging
import os

import aiohttp
import asyncpg

DB_DSN = os.getenv("DB_DSN", "postgresql://postgres:password@adsb-db:5432/adsb")
SLEEP_INTERVAL = os.getenv("SLEEP_INTERVAL", "60")
CONFIG_PATH = os.getenv("FILTER_PATH", '/app/adsb-alerts/filters.json')
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ALERT_PARAMS = os.getenv("ALERT_PARAMS", "hex, flight")
MAX_DISCORD_RETRIES = os.getenv("MAX_DISCORD_RETRIES", "3")

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

async def fetch_last_aircraft(pool, max_age_seconds: str) -> list:
    """ Fetch the latest added aircraft from the DB. """
    query = """
        SELECT 
            a.*, 
            p.* 
        FROM aircraft a
        LEFT JOIN (
            -- PostgreSQL specific syntax to get the most recent row per hex
            SELECT DISTINCT ON (hex) 
                hex, lat, lon, alt_baro, alt_geom, gs, track, squawk, timestamp
            FROM position
            ORDER BY hex, timestamp DESC
        ) p ON a.hex = p.hex
        WHERE last_updated >= NOW() - ($1 || ' seconds')::interval
    """
    
    async with pool.acquire() as conn:
        return await conn.fetch(query, max_age_seconds)

def filter_aircraft(ac: dict, ac_filter: dict) -> dict:
    """ Return an aircraft is it matches an alert filter."""
    if not ac_filter:
        return {}
    for k, expected_value in ac_filter.items():
        if k not in ac or ac[k] != expected_value:
            # Either key not in ac data or value does not match
            return {}
    # end of loop is only reached if every key is present and matches
    return ac

async def dispatch_alert(session, ac: dict, webhook: str):
    """ Send alert to discord."""
    # Create a list of the fields to alert on
    alert_params = [k.strip() for k in ALERT_PARAMS.split(',') if k.strip()]
    logging.debug(f"Looking for alert params: {alert_params} in {list(ac.keys())}")
    # Copy the data we want to send in the alert from the ac dict
    alert_data = {k: ac[k] for k in alert_params if k in ac}
    logging.debug(f"Using alert_data: {alert_data}")
    payload = {
        "content": f"**Aircraft Alert!**\n```json\n{json.dumps(alert_data, indent=2)}\n```"
    }
   # Send the payload to discord 
    for attempt in range(int(MAX_DISCORD_RETRIES)):
        try:
            async with session.post(url=webhook, json=payload) as response:
                if response.ok:
                    return True

                if response.status == 429:
                    # Rate limiting, back off dynamically, default to 1s
                    res_json = response.json()
                    retry_after = res_json.get('retry_after', 1.0)
                    logging.warning(f"""
                        Discord rate limiting encountered,backing off for
                        {retry_after} s, attempt {attempt + 1}/{MAX_DISCORD_RETRIES}
                    """)
                    await asyncio.sleep(retry_after)
                    continue

                # log failures
                error = await response.text()
                logging.error(f"Failed to send alert to discord with {response.status}: {error}")
                return False
        except aiohttp.ClientError() as e:
            logging.error(f"Networking error sending webhook: {e}")
            return False

async def main():
    db_pool = await asyncpg.create_pool(dsn=DB_DSN)
    active_alerts = {}

    # 1. Create the session ONCE outside the loop
    async with aiohttp.ClientSession() as session:

        try:
            while True:
                # 1. Non-blocking ConfigMap read (via thread)
                ac_filters = await asyncio.to_thread(read_filters, CONFIG_PATH)

                # 2. Non-blocking DB query
                new_aircraft = await fetch_last_aircraft(db_pool, SLEEP_INTERVAL)
                logging.debug(f"Received {len(new_aircraft)} from database")

                # 3. Process results
                for ac in new_aircraft:
                    # Check all filters for each aircraft
                    for f_name, f_conf in ac_filters.items():
                        matching_ac = filter_aircraft(ac, f_conf)
                        if matching_ac:
                            logging.info(f"Found match for aircraft {ac['hex']} in filter {f_name}")
                            # Alert to discord if this alert is not already active
                            if (ac.get('hex') not in active_alerts and
                               f_conf.get('status', 'enabled').lower() == 'enabled'):
                                # Send alert to discord
                                success = await dispatch_alert(session, ac, DISCORD_WEBHOOK)
                                if success:
                                    logging.debug(f"Successfully sent alert to discord for hex {ac['hex']}")
                                    active_alerts[ac['hex']] = datetime.now(timezone.utc)
                                else:
                                    logging.warning(f"Failed to send alert for hex {ac.get('hex')}")
                
                # Cleanup active alerts older than 1 hour (3600 seconds)
                now = datetime.now(timezone.utc)
                active_alerts = {
                    hex_code: ts for hex_code, ts in active_alerts.items() 
                    if (now - ts).total_seconds() < 3600
                }
                
                await asyncio.sleep(int(SLEEP_INTERVAL))
        finally:
            await db_pool.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
