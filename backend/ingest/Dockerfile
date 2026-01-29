# STAGE 1: Builder
FROM python:3.11-slim AS builder

# Install build tools for AWS Lambda RIC
RUN apt-get update && apt-get install -y \
    g++ \
    make \
    cmake \
    unzip \
    libcurl4-openssl-dev

# Copy ingestion specific requirements
# Context is project root, so we include the full path
COPY backend/ingest/ingest_requirements.txt .

# Install dependencies + RIC
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
    --target /install \
    awslambdaric \
    -r ingest_requirements.txt

# STAGE 2: Final Runtime
FROM python:3.11-slim

ARG LAMBDA_TASK_ROOT="/var/task"

# Install SSL certs (Critical for Google GenAI / Pinecone / Neo4j)
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy libs from builder
COPY --from=builder /install /usr/local/lib/python3.11/site-packages

WORKDIR ${LAMBDA_TASK_ROOT}

# Copy your code (Renaming ingest.py -> lambda_function.py)
COPY backend/ingest/ingest.py ${LAMBDA_TASK_ROOT}/lambda_function.py

# Entrypoint for Lambda
ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]

# Command (Refers to the handler function inside ingest.py)
CMD [ "lambda_function.lambda_handler" ]