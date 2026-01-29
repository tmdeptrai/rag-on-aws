#!/bin/bash
set -e
export AWS_PAGER=""

# Navigate to script folder
cd "$(dirname "$0")"

echo "STARTING FULL DEPLOYMENT..."

./deploy_query.sh
echo "-----------------------------------"
./deploy_ingest.sh

echo "ALL SYSTEMS DEPLOYED!"