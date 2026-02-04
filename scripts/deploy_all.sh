#!/bin/bash
set -e
export AWS_PAGER=""

# 1. Navigate to Project Root
cd "$(dirname "$0")/.."

# 2. CI/Local Logic: Load .env only if it exists
if [ -f .env ]; then
    echo "Loading configuration from .env..."
    set -a
    source <(sed 's/[[:space:]]*=[[:space:]]*/=/g' .env)
    set +a
else
    echo ".env file not found. Assuming environment variables are set (CI Mode)."
fi

# 3. Validation: Ensure required variables exist
: "${AWS_ACCOUNT_ID:?Need to set AWS_ACCOUNT_ID}"
: "${AWS_REGION:?Need to set AWS_REGION}"
: "${ECR_REPO_INGEST:?Need to set ECR_REPO_INGEST}"
: "${LAMBDA_FUNC_INGEST:?Need to set LAMBDA_FUNC_INGEST}"

echo "   DEPLOYING INGEST SERVICE..."
echo "   Repo: $ECR_REPO_INGEST"
echo "   Function: $LAMBDA_FUNC_INGEST"
echo "   Region: $AWS_REGION"

# 4. Login (Using standard AWS_REGION)
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

# 5. Build
docker build -t "$ECR_REPO_INGEST" -f backend/ingest/Dockerfile .

# 6. Tag & Push
docker tag "$ECR_REPO_INGEST:latest" "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_INGEST:latest"
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_INGEST:latest"

# 7. Update Lambda
aws lambda update-function-code --function-name "$LAMBDA_FUNC_INGEST" --image-uri "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_INGEST:latest"

echo "Ingest Service Deployed Successfully!"