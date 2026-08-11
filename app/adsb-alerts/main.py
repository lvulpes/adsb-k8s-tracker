import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import re

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

def filter_aircraft(ac: dict, filter_conf: dict) -> dict:
    """ Return an aircraft is it matches an alert filter."""
    if 'metadata' in ac_filter:
        ac_filter = filter_conf.copy()
        ac_filter.pop("metadata")
    else:
        ac_filter = filter_conf
    if not ac_filter:
        return {}

    for k, expected_value in ac_filter.items():
        re_pattern = fr"^{expected_value}$"
        if k not in ac or not re.fullmatch(re_pattern, ac[k]):
            # Either key not in ac data or value does not match
            return {}
    # end of loop is only reached if every key is present and matches
    return ac

async def dispatch_alert(session, ac: dict, webhook: str, f_conf: dict):
    """ Send alert to discord."""
    # Create a list of the fields to alert on
    alert_params = [k.strip() for k in ALERT_PARAMS.split(',') if k.strip()]
    # Copy the data we want to send in the alert from the ac dict
    alert_data = {k: ac[k] for k in alert_params if k in ac}
    # Add filter text from metadata
    metadata = f_conf.get('metadata') or {}
    if 'filter_text' in metadata:
        alert_data['filter_text'] = metadata['filter_text']

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
    """ Send alerts to discord for new flights based on configs. """
    db_pool = await asyncpg.create_pool(dsn=DB_DSN)
    active_alerts = {}

    # 1. Create the session ONCE outside the loop
    async with aiohttp.ClientSession() as session:

        try:
            while True:
                # Non-blocking ConfigMap read (via thread)
                ac_filters = await asyncio.to_thread(read_filters, CONFIG_PATH)

                # Non-blocking DB query, fetches last updated since SLEEP_INTERVAL
                new_aircraft = await fetch_last_aircraft(db_pool, SLEEP_INTERVAL)
                logging.debug(f"Received {len(new_aircraft)} from database")

                # Process results
                for ac in new_aircraft:
                    # Check all filters for each aircraft
                    hex_code = ac.get('hex')

                    for f_name, f_conf in ac_filters.items():
                        if not filter_aircraft(ac, f_conf):
                            continue
                        if f_conf.get("status", "enabled").lower() != 'enabled':
                            continue
                        logging.info(f"Found match for aircraft {hex_code} in filter {f_name}")

                        # If alert is already active, update timestamp
                        if hex_code in active_alerts:
                            active_alerts[hex_code] = datetime.now(timezone.utc)
                            continue
                        # New alert, dispatch notification
                        success = await dispatch_alert(session, ac, DISCORD_WEBHOOK, f_conf)
                        if success:
                            logging.debug(f"Successfully sent alert to discord for hex {hex_code}")
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
