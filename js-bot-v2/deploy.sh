#!/bin/bash
# One-click deploy script for enhanced v2 bot to Fly.io
# Run this from js-bot-v2/ directory on your Mac

set -e

echo "=== Enhanced Crypto Bot v2 - Fly.io Deployment ==="
echo ""

# Check if flyctl is installed
if ! command -v fly &> /dev/null; then
    echo "Installing flyctl..."
    curl -L https://fly.io/install.sh | sh
    export FLYCTL_INSTALL="$HOME/.fly"
    export PATH="$FLYCTL_INSTALL/bin:$PATH"
fi

# Check if logged in
if ! fly auth whoami &> /dev/null; then
    echo "Please log in to Fly.io..."
    fly auth login
fi

# Launch the app (first time only - will skip if already exists)
if ! fly status --app bitunix-crypto-agent-v2 &> /dev/null; then
    echo "Creating new Fly.io app..."
    fly launch --copy-config --name bitunix-crypto-agent-v2 --no-deploy --yes
fi

# Prompt for secrets
echo ""
echo "=== Setting API secrets ==="
read -p "Bitunix API Key: " BITUNIX_API_KEY
read -s -p "Bitunix Secret Key: " BITUNIX_SECRET_KEY
echo ""
read -p "Anthropic API Key (optional, press enter to skip): " ANTHROPIC_API_KEY

fly secrets set \
    BITUNIX_API_KEY="$BITUNIX_API_KEY" \
    BITUNIX_SECRET_KEY="$BITUNIX_SECRET_KEY" \
    ${ANTHROPIC_API_KEY:+ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY"} \
    --app bitunix-crypto-agent-v2

# Deploy
echo ""
echo "=== Deploying to Fly.io ==="
fly deploy --app bitunix-crypto-agent-v2

# Open in browser
echo ""
echo "=== Done! Opening dashboard ==="
fly open --app bitunix-crypto-agent-v2

echo ""
echo "Your v2 bot is live! Compare with v1 on Railway."
echo "View logs anytime with: fly logs --app bitunix-crypto-agent-v2"
