#!/usr/bin/env bash

# Stop execution if any command fails
set -e

echo "Installing project from scratch"

if [[ "$1" != "" ]]; then
    echo "Creating cluster $1"
    MY_CLUSTER=$1
elif [[ "$1" == "" ]]; then
    echo "Need at least 1 arg!"
else
    echo "something else"
fi

if [ "$INFISICAL_CLIENT_SECRET" = "" ] || [ "$INFISICAL_TOKEN" = "" ] || [ "$INFISICAL_CLIENT_ID" = "" ]; then
    echo "Infisical env variables must be set!"
    exit 1
else
    echo "Infisical env variables are set, proceeding with installation..."
fi

k3d cluster create $MY_CLUSTER -p "8080:80@loadbalancer"

# 1. Add the official ESO repository
helm repo add external-secrets https://charts.external-secrets.io
helm repo update

echo "Installing ESO CRD..."
# 2. Install the operator itself and force CRD creation
helm upgrade --install external-secrets external-secrets/external-secrets \
    --namespace external-secrets \
    --create-namespace \
    --set installCRDs=true
