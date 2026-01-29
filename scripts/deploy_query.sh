#!/bin/bash
set -e # Stop script on first error

# 1. Navigate to Project Root (so we can find .env and Dockerfile)
cd "$(dirname "$0")/.."

# 2. Load Environment Variables from .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "❌ Error: .env file not found in project root."
    exit 1
fi

echo "🚀 DEPLOYING QUERY SERVICE..."
echo "   Repo: $ECR_REPO_QUERY"
echo "   Function: $LAMBDA_FUNC_QUERY"

# 3. Login to ECR
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# 4. Build
# Note: Context is '.' (root), Dockerfile path is explicit
docker build -t $ECR_REPO_QUERY -f backend/query/Dockerfile .

# 5. Tag & Push
docker tag $ECR_REPO_QUERY:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_QUERY:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_QUERY:latest

# 6. Update Lambda
aws lambda update-function-code --function-name $LAMBDA_FUNC_QUERY --image-uri $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_QUERY:latest

echo "✅ Query Service Deployed Successfully!"