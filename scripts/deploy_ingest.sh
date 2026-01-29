#!/bin/bash
set -e
export AWS_PAGER=""

# 1. Navigate to Project Root
cd "$(dirname "$0")/.."

# 2. Load .env safely
if [ -f .env ]; then
    set -a
    source <(sed 's/[[:space:]]*=[[:space:]]*/=/g' .env)
    set +a
else
    echo "Error: .env file not found."
    exit 1
fi

echo "DEPLOYING INGEST SERVICE..."
echo "   Repo: $ECR_REPO_INGEST"
echo "   Function: $LAMBDA_FUNC_INGEST"

# 3. Login
aws ecr get-login-password --region "$REGION_NAME" | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$REGION_NAME.amazonaws.com"

# 4. Build
docker build -t "$ECR_REPO_INGEST" -f backend/ingest/Dockerfile .

# 5. Tag & Push
docker tag "$ECR_REPO_INGEST:latest" "$AWS_ACCOUNT_ID.dkr.ecr.$REGION_NAME.amazonaws.com/$ECR_REPO_INGEST:latest"
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$REGION_NAME.amazonaws.com/$ECR_REPO_INGEST:latest"

# 6. Update Lambda
aws lambda update-function-code --function-name "$LAMBDA_FUNC_INGEST" --image-uri "$AWS_ACCOUNT_ID.dkr.ecr.$REGION_NAME.amazonaws.com/$ECR_REPO_INGEST:latest"

echo "Ingest Service Deployed Successfully!"