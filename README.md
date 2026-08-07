# adsb-k8s-tracker
A kubernetes deployment of an adsb receiver for flight tracking.

# Goal
This is a learning project to get familiar with ads-b reception using SDR, deployment using kubernetes as well as alerting and monitoring.

# Function
- A local server pulls adsb data from public API endpoints
- Pulled data is filtered according to [filter rules](./charts/adsb-api/templates/configmap.yaml) and stored in a postgresql db
- A local RTL-SDR is used to decode ADS-B from local flights (stored under in-situ filter)
- Data from DB is displayed on a website (LAN only for now)
- Last minutes data is continuously evaluated against [notification rules](./charts/adsb-alerts/templates/configmap.yaml), matches are alerted on Discord

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
