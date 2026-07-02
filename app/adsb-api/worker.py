from datetime import datetime
from geopy.distance import great_circle
import json
import logging
import os
import requests
import time

PATH = "/app"
CONFIG_PATH = PATH + '/adsb-api/config.json'
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
	level=getattr(logging, LOG_LEVEL, logging.INFO),
	format="%(asctime)s [%(levelname)s] %(message)s",
)
logging.info(f"Logger initialized at level: {LOG_LEVEL}")

def calculate_distance(point_1: tuple, point_2: tuple, unit='km') -> float:
	""" Take 2 sets of coordinates and calculate the distance. """
	dist = great_circle(point_1, point_2)
	if unit.lower() == 'nm':
		return dist.nm
	else:
		return dist.km

def within_poi(ac_data: dict, poi: dict) -> bool:
	""" Return aircraft if it's inside the poi. """
	if 'lat' not in ac_data or 'lon' not in ac_data:
		return False
	ac_pos = (ac_data['lat'], ac_data['lon'])
	poi_pos = (poi['lat'], poi['lon'])
	dis = calculate_distance(ac_pos, poi_pos, unit=poi['unit'])
	return dis <= float(poi['distance'])

def poi_filter(filter_conf: dict, aircraft: list) -> list:
	return [ac for ac in aircraft if within_poi(ac, filter_conf['coordinates'])]

def get_adsb_feed(URL: str) -> dict:
	headers = {
	}
	try:
		response = requests.get(URL, headers = headers)
		response.raise_for_status()

	except requests.exceptions.Timeout as e:
		# Crucial for a background loop so one stalled request doesn't hang the worker
		logging.error(f"ADS-B Exchange API timeout occurred: {e}")
		# Target for a backoff or simple pass to try again on the next tick

	except requests.exceptions.HTTPError as e:
		# Catches 4xx/5xx responses (e.g., rate limits, bad API key, service down)
		logging.error(f"ADS-B Exchange returned an HTTP error status: {e}")
		if e.response.status_code == 429:
			logging.warning("Rate limit hit. Implementing backing off strategy.")

	except requests.exceptions.ConnectionError as e:
		# Catches DNS failures, network drops, or API endpoint routing changes
		logging.error(f"Failed to connect to ADS-B Exchange server: {e}")

	except requests.exceptions.RequestException as e:
		# Catch-all for any ambiguous issues handling the request itself
		logging.error(f"Ambiguous request error occurred during data fetch: {e}")

	except (KeyError, ValueError) as e:
		# Catches payload structure changes or malformed JSON parsing failures
		logging.error(f"Failed to parse payload structure from incoming API data: {e}")

	except:
		logging.error(f"Failed due to unspecified error: {e}")

	else:
		return response.json()

def main() -> None:
	logging.info("Starting app...")
	logging.info("Reading config...")
	with open(CONFIG_PATH, 'r', encoding='utf-8') as conf:
		config = json.load(conf)
		
	aircraft_data = {}

	while(True):
		for query in config['endpoints'].keys():
			# Add returned data under each key, sleep due to rate limiting
			logging.info("Getting ADS-B data from API...")
			aircraft_data[query] = get_adsb_feed(config['endpoints'][query]['url'])
			time.sleep(1)
			# Attach config data to use later
			aircraft_data[query].update(config['endpoints'][query])
		# end of workflow, sleep for 60s
		time.sleep(59)
	
	logging.info("Reached end!")	

