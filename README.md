# adsb-k8s-tracker
A kubernetes deployment of an adsb receiver for flight tracking.

# Goal
This is a learning project to get familiar with ads-b reception using SDR, deployment using kubernetes as well as alerting and monitoring.

# Function
- A local server pulls adsb data from public API endpoints
- Pulled data is filtered according to filter rules (Infisical key `api_flights.json`, synced via [ExternalSecret](./charts/adsb-api/templates/adsb-api-secret.yaml)) and stored in a postgresql db
- Military aircraft (adsb.fi `/mil`) are matched against tracking lists: every Infisical key starting with `tracking-` is a YAML list of aircraft (`hex` takes precedence over `reg`), synced via [ExternalSecret](./charts/adsb-api/templates/adsb-api-secret.yaml). Matches are stored with the key name as filter
- A local RTL-SDR is used to decode ADS-B from local flights (stored under in-situ filter)
- Data from DB is displayed on a website (LAN only for now)
- Last minutes data is continuously evaluated against notification rules (Infisical key `alerts_filters.json`, synced via [ExternalSecret](./charts/adsb-alerts/templates/adsb-alerts-secret.yaml)), matches are alerted on Discord. Tracking list entries with `alerting: enabled` are alerted on too, with `"{comment} from {unit}"` as alert text

# Architecture

```text
+----------------+       +-------------------+       +------------------+
|  RTL-SDR Dongle| ----> |  adsb-decoder     |       |  adsb-exchange   |
|  (Hardware)    |       |  (readsb/tar1090) |       |  (External API)  |
+----------------+       +---------+---------+       +--------+---------+
                                   ^                          |
                                   | (Reads)                  | (API Calls)
                                   | (TCP/30003)              v
                         +-------------------+       +------------------+
                         |  adsb-ingestor    | <---->|  adsb-api        |
                         |  (Python/Node)    |       |  (Filter Logic)  |
                         |  - Normalizes     |       |  - Filters       |
                         |  - Writes to DB   |       |  - Enriches      |
                         +---------+---------+       +--------+---------+
                                   |                          |
                                   | (Writes)                 | (Reads)
                                   v                          v
                         +-------------------+       +------------------+
                         |  adsb-db          | <---->|  adsb-alerts     |
                         |  (Postgres/Influx)|       |  (Logic Engine)  |
                         |  - Flight Tracks  |       |  - Triggers      |
                         |  - Metadata       |       |  - Webhooks      |
                         +---------+---------+       +--------+---------+
                                   |                          |
                                   | (Query)                  | (Notify)
                                   v                          v
                         +-------------------+       +------------------+
                         |  adsb-ui          |       |  Notification    |
                         |  (React/Nginx)    |       |  (Discord)       |
                         |  - Maps           |       +------------------+
                         |  - History        |
                         +-------------------+

                         +-------------------+
                         |  adsb-gateway     |
                         |  (Nginx Ingress   |
                         |   or NodePort)    |
                         +-------------------+
```
