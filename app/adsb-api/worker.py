import json
import logging
import os
import time

from geopy.distance import great_circle
import requests

PATH = "/app"
CONFIG_PATH = PATH + '/adsb-api/config.json'
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
INGESTOR_URL = os.getenv("INGESTOR_URL", "")

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
    return dist.km

def within_poi(ac_data: dict, poi: dict) -> bool:
    """ Return aircraft if it's inside the poi. """
    if 'lat' not in ac_data or 'lon' not in ac_data:
        if 'rr_lat' not in ac_data or 'rr_lon' not in ac_data:
            logging.debug(f"No position found in ac dict: {ac_data}")
            return False
        else:
            # No exact pos, get ground estimate
            lat_key = 'rr_lat'
            lon_key = 'rr_lon'
    else:
        # Exact pos broadcast by ac
        lat_key = 'lat'
        lon_key = 'lon'
    ac_pos = (ac_data[lat_key], ac_data[lon_key])
    poi_pos = (poi['lat'], poi['lon'])
    dis = calculate_distance(ac_pos, poi_pos, unit=poi['unit'])
    logging.debug(f"Calculated distance for icao {ac_data['hex']} is {dis}")
    return dis <= float(poi['distance'])

def poi_filter(filter_conf: dict, aircraft: list) -> list:
    """ Return list of aircraft inside the poi. """
    return [ac for ac in aircraft if within_poi(ac, filter_conf['coordinates'])]

def icao_filter(filter_conf: dict, aircraft: list) -> list:
    """ Return list of aicraft on the list. """
    return [ac for ac in aircraft if ac['hex'].lower() in filter_conf['icao_list']]

def get_adsb_feed(url: str) -> dict:
    """ Get aircraft data from API given by , return json. """
    headers = {
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

    except requests.exceptions.Timeout as e:
        # Crucial for a background loop so one stalled request doesn't hang the worker
        logging.error(f"ADS-B API timeout occurred: {e}")
        # Target for a backoff or simple pass to try again on the next tick

    except requests.exceptions.HTTPError as e:
        # Catches 4xx/5xx responses (e.g., rate limits, bad API key, service down)
        logging.error(f"ADS-B API returned an HTTP error status: {e}")
        if e.response.status_code == 429:
            logging.warning("Rate limit hit. Implementing backing off strategy.")

    except requests.exceptions.ConnectionError as e:
        # Catches DNS failures, network drops, or API endpoint routing changes
        logging.error(f"Failed to connect to ADS-B API server: {e}")

    except requests.exceptions.RequestException as e:
        # Catch-all for any ambiguous issues handling the request itself
        logging.error(f"Ambiguous request error occurred during data fetch: {e}")

    except (KeyError, ValueError) as e:
        # Catches payload structure changes or malformed JSON parsing failures
        logging.error(f"Failed to parse payload structure from incoming API data: {e}")

    except Exception as e:
        logging.error(f"Failed due to unspecified error: {e}")

    else:
        return response.json()['ac']

def ship_to_ingestor(payload: list) -> None:
    """ Take aircraft dictionaries and ship it to the ingestor pod. """
    try:
        requests.post(INGESTOR_URL, json=payload, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"Failed to ship payload to ingestor service: {e}")
    else:
        logging.debug(f"Shipped to ingestor: {payload}")
        logging.info(f"Shipped {len(payload)} aircraft to ingestor")


def main() -> None:
    """ Get adsb data for each endpoint and apply filter, push to ingestor."""
    logging.info("Starting app...")
    logging.info("Reading config...")
    with open(CONFIG_PATH, 'r', encoding='utf-8') as conf:
        config = json.load(conf)

    aircraft_data = {}

    while True:
        for query in config['endpoints'].keys():
            logging.info("Getting ADS-B data from API...")
            endpoint_config = config['endpoints'][query]
            aircraft_data[query] = get_adsb_feed(endpoint_config['url'])
            time.sleep(1)

            if aircraft_data[query] is None:
                # No data returned from this endpoint, continue with next
                logging.warning(f"No aircraft data returned from {query} endpoint")
                continue

            # Check that there is a filter set for the endpoint
            if 'filter' not in endpoint_config:
                raise KeyError("Filter is mandatory for each query")
            query_filter = endpoint_config['filter']

            # Check that the filter is defined
            if query_filter not in config['filters']:
                raise KeyError("Chosen filter is not defined")
            
            # Get the filter config
            filter_config = config['filters'][query_filter]

            # Check what kind of filter it is
            if filter_config['kind'] == 'poi':
                # Do poi filtering
                logging.info(f"Sending {len(aircraft_data[query])} to poi_filter")
                filtered_ac = poi_filter(filter_config, aircraft_data[query])
            elif filter_config['kind'] == 'icao':
                # Do icao filtering
                logging.info(f"Sending {len(aircraft_data[query])} to icao_filter")
                filtered_ac = icao_filter(filter_config, aircraft_data[query])
                logging.info(f"Got {len(filtered_ac)} aircraft from icao filter")
            elif filter_config['kind'] == 'callsign':
                # Do callsign filtering
                raise NotImplementedError("callsign filtering is not implemented")

            # Push json to ingestor which ships it to database, if any
            if filtered_ac:
                for ac in filtered_ac:
                    # Add the filter that was used
                    ac['filter'] = query_filter
                ship_to_ingestor(filtered_ac)
            else:
                logging.warning(f"filter returned {len(filtered_ac)} aircraft for {query_filter}")
        # end of workflow, sleep for 60s
        time.sleep(59)

    logging.info("Reached end!")
