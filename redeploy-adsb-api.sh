#!/usr/bin/env bash
set -e

echo "Building images..."
docker build --build-arg COMPONENT=adsb-api -t adsb-api:local .
docker build --build-arg COMPONENT=adsb-ingestor -t adsb-ingestor:local .

echo "Importing to cluster..."
k3d image import adsb-api:local -c hugin-cluster
k3d image import adsb-ingestor:local -c hugin-cluster

echo "Deploying infrastructure..."
kubectl create secret generic infisical-auth \
    --from-literal=clientId="$INFISICAL_CLIENT_ID" \
    --from-literal=clientSecret="$INFISICAL_CLIENT_SECRET" \
    --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install cluster-infra ./charts/cluster-infra
helm upgrade --install adsb-db oci://registry-1.docker.io/bitnamicharts/postgresql -f charts/adsb-db/values.yaml

echo "Deploying components..."
helm upgrade --install adsb-api ./charts/adsb-api
helm upgrade --install adsb-ingestor ./charts/adsb-ingestor

echo "Restarting deployment..."
kubectl rollout restart deployment adsb-api-deployment
kubectl rollout restart deployment adsb-ingestor-deployment

echo -e "\nFinished redeployment! Go ahead and tail the logs:"
echo "kubectl logs -f -l \"app.kubernetes.io/name in (adsb-api, adsb-ingestor)\""
