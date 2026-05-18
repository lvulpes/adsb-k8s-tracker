# adsb-k8s-tracker
A kubernetes deployment of an adsb receiver for flight tracking.

# Goal
This is a learning project to get familiar with ads-b reception using SDR, deployment using kubernetes as well as alerting and monitoring.

# Architecture

+----------------+       +-------------------+       +------------------+
|  RTL-SDR Dongle| ----> |  adsb-decoder     |       |  adsb-exchange   |
|  (Hardware)    |       |  (readsb/tar1090) |       |  (External API)  |
+----------------+       +---------+---------+       +--------+---------+
                                   |                          |
                                   | (Live Stream)            | (API Calls)
                                   v                          v
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
                         |  (React/Nginx)    |       |  (Discord/Email) |
                         |  - Maps           |       +------------------+
                         |  - History        |
                         +-------------------+

+-------------------+       +-------------------+
|  adsb-monitoring  |       |  adsb-gateway     |
|  (Prometheus/     |       |  (Nginx Ingress   |
|   Grafana)        |       |   or NodePort)    |
+-------------------+       +-------------------+
