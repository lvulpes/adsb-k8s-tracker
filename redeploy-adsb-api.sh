#!/usr/bin/env bash

docker build -t adsb-api:local .
k3d image import adsb-api:local -c hugin-cluster
kubectl rollout restart deployment adsb-api-deployment

echo "Finished redeployment, go ahead and tail the logs!\n"
