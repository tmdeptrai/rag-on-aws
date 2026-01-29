#!/bin/bash
set -e

# 1. Navigate to Project Root
cd "$(dirname "$0")/.."

# 2. Load .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "❌ Error: .env file not found."
    exit 1
fi

echo "🚀 DEPLOYING INGEST SERVICE..."
echo "   Repo: $ECR_REPO_INGEST"
echo "   Function: $LAMBDA_FUNC_INGEST"

# 3. Login
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# 4. Build
docker build -t $ECR_REPO_INGEST -f backend/ingest/Dockerfile .

# 5. Tag & Push
docker tag $ECR_REPO_INGEST:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_INGEST:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_INGEST:latest

# 6. Update Lambda
aws lambda update-function-code --function-name $LAMBDA_FUNC_INGEST --image-uri $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_INGEST:latest

echo "✅ Ingest Service Deployed Successfully!"