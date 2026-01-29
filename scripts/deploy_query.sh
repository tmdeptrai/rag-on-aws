#!/bin/bash
set -e
export AWS_PAGER=""

# 1. Navigate to Project Root
cd "$(dirname "$0")/.."

# 2. Load .env safely (stripping spaces around '=' and handle special characters)
if [ -f .env ]; then
    set -a
    # This magic line removes spaces around the '=' before sourcing
    source <(sed 's/[[:space:]]*=[[:space:]]*/=/g' .env)
    set +a
else
    echo "Error: .env file not found."
    exit 1
fi

echo "DEPLOYING QUERY SERVICE..."
echo "   Repo: $ECR_REPO_QUERY"
echo "   Function: $LAMBDA_FUNC_QUERY"

# 3. Login to ECR
aws ecr get-login-password --region "$REGION_NAME" | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$REGION_NAME.amazonaws.com"

# 4. Build
docker build -t "$ECR_REPO_QUERY" -f backend/query/Dockerfile .

# 5. Tag & Push
docker tag "$ECR_REPO_QUERY:latest" "$AWS_ACCOUNT_ID.dkr.ecr.$REGION_NAME.amazonaws.com/$ECR_REPO_QUERY:latest"
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$REGION_NAME.amazonaws.com/$ECR_REPO_QUERY:latest"

# 6. Update Lambda
aws lambda update-function-code --function-name "$LAMBDA_FUNC_QUERY" --image-uri "$AWS_ACCOUNT_ID.dkr.ecr.$REGION_NAME.amazonaws.com/$ECR_REPO_QUERY:latest"

echo "Query Service Deployed Successfully!"