#!/bin/bash
set -e

# Navigate to script folder so we can call siblings easily
cd "$(dirname "$0")"

echo "📦 STARTING FULL DEPLOYMENT..."

./deploy_query.sh
echo "-----------------------------------"
./deploy_ingest.sh

echo "🎉 ALL SYSTEMS DEPLOYED!"