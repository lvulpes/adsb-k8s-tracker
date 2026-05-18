# adsb-k8s-tracker
A kubernetes deployment of an adsb receiver for flight tracking.

# Goal
This is a learning project to get familiar with ads-b reception using SDR, deployment using kubernetes as well as alerting and monitoring.

# Architecture
graph TD
    subgraph Hardware
        SDR[RTL-SDR Dongle]
    end

    subgraph "K8s Cluster"
        Decoder[adsb-decoder <br/> readsb/tar1090]
        Ingestor[adsb-ingestor <br/> Python/Node]
        DB[(adsb-db <br/> Postgres/Influx)]
        API[adsb-api <br/> Filter Logic]
        Alerts[adsb-alerts <br/> Logic Engine]
        UI[adsb-ui <br/> React/Nginx]
        Mon[adsb-monitoring <br/> Prometheus/Grafana]
        GW[adsb-gateway <br/> Ingress]
    end

    subgraph External
        Exchange[adsb-exchange <br/> External API]
        Notify[Notifications <br/> Discord/Email]
    end

    SDR -->|Raw Data| Decoder
    Decoder -->|Live Stream| Ingestor
    Exchange -->|API Calls| API
    Ingestor -->|Writes| DB
    DB <-->|Reads/Queries| API
    API <-->|Enriches| Alerts
    API -->|Query| UI
    Alerts -->|Notify| Notify
    
    style SDR fill:#f9f,stroke:#333,stroke-width:2px
    style DB fill:#77dd77,stroke:#333,stroke-width:2px
    style UI fill:#aec6cf,stroke:#333,stroke-width:2px
