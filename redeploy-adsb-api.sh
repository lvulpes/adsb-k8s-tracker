#!/usr/bin/env bash
set -e

# get cluster name from arg
if [[ "$1" != "" ]]; then
    CLUSTER_NAME=$1
    echo "Redeploying in cluster $CLUSTER_NAME..."
elif [[ "$1" == "" ]]; then
    echo "Using default cluster name hugin-cluster"
    CLUSTER_NAME="hugin-cluster"
fi

uv sync

echo "Building images..."
docker build --build-arg COMPONENT=adsb-api -t adsb-api:local .
docker build --build-arg COMPONENT=adsb-ingestor -t adsb-ingestor:local .
docker build --build-arg COMPONENT=adsb-ui -t adsb-ui:local .

echo "Importing to cluster..."
k3d image import adsb-api:local -c $CLUSTER_NAME
k3d image import adsb-ingestor:local -c $CLUSTER_NAME
k3d image import adsb-ui:local -c $CLUSTER_NAME

echo "Deploying infrastructure..."
kubectl create secret generic infisical-auth \
    --from-literal=clientId="$INFISICAL_CLIENT_ID" \
    --from-literal=clientSecret="$INFISICAL_CLIENT_SECRET" \
    --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install cluster-infra ./charts/cluster-infra
echo "Waiting for External Secrets webhook to be ready..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=external-secrets-webhook -n external-secrets --timeout=60s
helm upgrade --install adsb-db oci://registry-1.docker.io/bitnamicharts/postgresql -f charts/cluster-infra/values.yaml
helm upgrade --install adsb-gateway ./charts/adsb-gateway

echo "Deploying components..."
helm upgrade --install adsb-api ./charts/adsb-api
helm upgrade --install adsb-ingestor ./charts/adsb-ingestor
helm upgrade --install adsb-ui ./charts/adsb-ui
helm upgrade --install adsb-decoder ./charts/adsb-decoder

echo "Restarting deployment..."
kubectl rollout restart deployment adsb-api-deployment
kubectl rollout restart deployment adsb-ingestor-deployment
kubectl rollout restart deployment adsb-ui-deployment
kubectl rollout restart deployment adsb-decoder-deployment

echo -e "\nFinished redeployment! Go ahead and tail the logs:"
echo "kubectl logs -f -l \"app.kubernetes.io/name in (adsb-api, adsb-ingestor, adsb-ui)\""
