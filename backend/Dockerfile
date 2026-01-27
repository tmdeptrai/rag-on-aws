# STAGE 1: Builder
FROM python:3.11-slim AS builder

# Install build tools for AWS Lambda RIC (Runtime Interface Client)
# 'g++' and 'make' are needed if binary wheels aren't found, but usually pip finds them.
# We include them just in case for robustness.
RUN apt-get update && apt-get install -y \
    g++ \
    make \
    cmake \
    unzip \
    libcurl4-openssl-dev

# Copy requirements
COPY backend/query-requirements.txt .

# Install dependencies + AWS Lambda RIC into /install
# We install awslambdaric manually here
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
    --target /install \
    awslambdaric \
    -r query-requirements.txt

# STAGE 2: Final Runtime
FROM python:3.11-slim

# Include global arg for Lambda Task Root
ARG LAMBDA_TASK_ROOT="/var/task"

# Install only critical runtime system libs
# ca-certificates is REQUIRED for Google GenAI / Pinecone SSL connections
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy python libraries from builder
COPY --from=builder /install /usr/local/lib/python3.11/site-packages

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy your code
COPY backend/query_raw.py ${LAMBDA_TASK_ROOT}/lambda_function.py
COPY .env ${LAMBDA_TASK_ROOT}/.env

# Set the Entrypoint to the AWS Lambda Runtime Interface Client
ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]

# Set the Command to your handler
CMD [ "lambda_function.lambda_handler" ]