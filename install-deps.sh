#!/usr/bin/env bash

# Stop execution if any command fails
set -e

# get user name from arg
if [[ "$1" != "" ]]; then
    echo "Installing dependencies for user $1"
    USER_NAME=$1
elif [[ "$1" == "" ]]; then
    echo "Need at least 1 arg!"
    exit 1
fi

echo "☕ Starting fika-fueled dependency installation for Pi 5..."

# 1. Install Docker
echo "--- Installing Docker ---"
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    echo "Docker installed successfully."
else
    echo "Docker is already installed, skipping..."
fi

# 2. Configure Docker Permissions for '$USER_NAME'
echo "--- Setting up Docker permissions for user '$USER_NAME' ---"
sudo usermod -aG docker $USER_NAME
echo "User '$USER_NAME' added to the docker group."

# 3. Install k3d
echo "--- Installing k3d ---"
if ! command -v k3d &>/dev/null; then
    curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
    echo "k3d installed successfully."
else
    echo "k3d is already installed, skipping..."
fi

# 4. Install Helm
echo "--- Installing Helm ---"
if ! command -v helm &>/dev/null; then
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
    echo "Helm installed successfully."
else
    echo "Helm is already installed, skipping..."
fi

# 5. Install kubectl (specifically for ARM64 / Raspberry Pi)
echo "--- Installing kubectl (arm64) ---"
if ! command -v kubectl &>/dev/null; then
    KUBECTL_VERSION=$(curl -L -s https://dl.k8s.io/release/stable.txt)
    curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/arm64/kubectl"
    sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
    rm kubectl
    echo "kubectl installed successfully."
else
    echo "kubectl is already installed, skipping..."
fi

# install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 6. Validation
echo "--- Validating Installations ---"
docker --version
k3d --version
helm version --short
kubectl version --client --output=yaml | grep gitVersion
uv --version

echo ""
echo "✅ All dependencies installed!"
echo "⚠️ IMPORTANT: To use Docker without sudo right now, you MUST run this command to refresh your group permissions:"
echo "    newgrp docker"
echo "Otherwise, log out of your SSH session and log back in."
