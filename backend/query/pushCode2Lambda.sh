#!/bin/bash

# 1. Login to ECR
aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin 379612263247.dkr.ecr.eu-west-1.amazonaws.com

# 2. Build the Image
docker build -t rag-on-aws -f ./backend/Dockerfile . || exit 1

# 3. Tag the Image
docker tag rag-on-aws:latest 379612263247.dkr.ecr.eu-west-1.amazonaws.com/rag-on-aws:latest

# 4. Push to ECR
docker push 379612263247.dkr.ecr.eu-west-1.amazonaws.com/rag-on-aws:latest || exit 1

# 5. Update Lambda
aws lambda update-function-code \
    --function-name queryLambda \
    --image-uri 379612263247.dkr.ecr.eu-west-1.amazonaws.com/rag-on-aws:latest

echo "Deployment Complete!"