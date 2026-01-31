# RAGwithAWS

Fully serverless Retrieval-Augmented Generation (RAG) application designed to run on AWS. The system ingests PDF documents into two knowledge stores (a vector database (Pinecone) for dense retrieval and a knowledge graph (Neo4j) for structured facts), then serves a Streamlit frontend that queries both and synthesizes answers using Google GenAI (Gemini).

## Table of contents
- Project overview
- Architecture
- Quickstart: Local development
- Run backend components locally (ingest & query)
- Docker: Build the Lambda-compatible artifacts
- Deploying to AWS (notes & scripts)
- Configuration: Environment variables & Streamlit secrets
- How it works: Implementation details
- Troubleshooting & diagnostics
- Security best practices
- Contributing
- License

---

## Project overview

This repository contains:
- frontend: Streamlit app (frontend/app.py) and helper clients
- backend/ingest: Lambda-style service to parse PDFs, create embeddings, and persist vectors & graph triples
- backend/query: Lambda-style service to perform hybrid retrieval (vector + Neo4j), then call an LLM for answer generation
- Dockerfiles for producing Lambda-ready runtimes
- Deploy scripts: scripts/deploy_all.sh, scripts/deploy_query.sh, scripts/deploy_ingest.sh
- Example environment variables: .env.example

Primary external services:
- AWS S3: document storage and trigger for ingestion
- AWS Cognito: user authentication for the front-end
- Pinecone: dense vector index for semantic retrieval
- Neo4j: knowledge graph for extracted triples and structured relationships
- Google GenAI (Gemini): embeddings and LLMs

---

## Architecture

<!-- DIAGRAM: High-Level System Architecture -->

High level flow:
1. User uploads PDF via Streamlit frontend -> saved to S3 (per-user prefix).
2. S3 event triggers ingest Lambda (backend/ingest/ingest.py).
3. Ingest Lambda:
   - Downloads PDF, extracts text (pymupdf), cleans and chunks text.
   - Calls Google GenAI to produce embeddings (gemini-embedding-001).
   - Upserts vectors into Pinecone (namespace = user email).
   - Generates a quick summary and extracts knowledge triples (Gemini schema), stores them in Neo4j.
   - Updates S3 object tags to indicate indexing status (uploaded, indexing, ready, failed).
4. User asks a question in the Streamlit app:
   - Frontend calls query Lambda (backend/query/query.py) with question and user_email.
   - Query Lambda does:
     - Vector search in Pinecone (top_k matches).
     - Generates a Cypher query via Gemini for graph retrieval, executes against Neo4j.
     - Combines vector and graph results and asks Gemini to synthesize the final answer.
   - Frontend displays answer and references.

---

## Quickstart: Local development

Prerequisites:
- Python 3.11 (recommended)
- pip
- Docker (for building runtime images)
- AWS CLI configured with credentials (if deploying to AWS)
- Accounts & credentials for: Pinecone, Neo4j (Aura or hosted), Google Cloud API (GenAI access), AWS (S3, Cognito, Lambda), and Pinecone.

1. Clone repository
   ```bash
   git clone https://github.com/tmdeptrai/rag-on-aws.git
   cd rag-on-aws
   ```

2. Copy `.env.example` to `.env` and fill in credentials OR set secrets as described below
   ```bash
   cp .env.example .env
   # Edit .env with real values
   ```

3. Install frontend dependencies and run Streamlit
   ```bash
   python -m pip install -r frontend/requirements.txt
   # Streamlit will read st.secrets via .streamlit/secrets.toml (see Configuration below)
   streamlit run frontend/app.py
   ```

4. Configure Streamlit secrets (recommended for local dev or prod — see Configuration section)

5. Use the UI to sign-up/login and upload a PDF. The upload will place the file into S3 using AWS credentials available in st.secrets. If the ingestion lambda is not deployed in AWS, you can simulate local ingestion (see Run backend components locally).

---

## Run backend components locally

Each backend module (ingest/query) contains a local test mode when executed directly. These are convenient for development and debugging.

Notes:
- The backend modules use python-dotenv to load `.env`.
- They assume remote services (Pinecone, Neo4j, Google GenAI) are reachable.

Run local ingest test:
```bash
python backend/ingest/ingest.py
```
This runs a small built-in test_event that points to the S3 bucket configured in `.env`. It will attempt to download the example file key from your S3 bucket. Update `.env` with valid S3 bucket name and credentials.

Run local query test:
```bash
python backend/query/query.py
```
This runs the built-in query test and requires Pinecone, Neo4j, and GenAI credentials.

If you want to test ingestion end-to-end without Lambda:
- Upload a PDF to your S3 bucket under the same key pattern expected by ingest.py (example: `documents/<user_email>/<filename>.pdf`) and then run ingest.py locally pointing to that key by adjusting the test_event in the file or invoking `lambda_handler` with a constructed event.

---

## Docker: Build the Lambda-compatible artifacts

The repository includes two Dockerfiles (backend/ingest/Dockerfile and backend/query/Dockerfile). These produce a runtime with dependencies installed into `/usr/local/lib/python3.11/site-packages` and copy the handler as `lambda_function.py` so the awslambdaric entrypoint can run the Lambda handler.

Build the ingest image (for local testing or to inspect collector contents):
```bash
docker build -t rag-ingest -f backend/ingest/Dockerfile .
```

Build the query image:
```bash
docker build -t rag-query -f backend/query/Dockerfile .
```

Note: These Dockerfiles are intended to create runtime packages for AWS Lambda. If you intend to deploy as Lambda functions with a container image, follow AWS Lambda container guidelines and push the built images to ECR, then create/update Lambda functions pointing at the ECR images. The provided Dockerfiles include awslambdaric so they are Lambda-compatible.

---

## Deploying to AWS

The repository contains scripts in `scripts/` to help with deployment:
- `scripts/deploy_all.sh` — runs deploy_query.sh and deploy_ingest.sh in sequence.

Typical steps to deploy:

1. Ensure AWS CLI is configured and you have permissions to create/update Lambda, IAM roles, S3, and Cognito resources.

2. Build and push container images (if using container-based Lambdas):
   - Build images (see Docker commands above).
   - Tag and push to ECR:
     ```bash
     aws ecr create-repository --repository-name rag-ingest || true
     aws ecr create-repository --repository-name rag-query || true

     # Example push flow:
     docker tag rag-ingest:latest <ACCOUNT>.dkr.ecr.<region>.amazonaws.com/rag-ingest:latest
     docker push <ACCOUNT>.dkr.ecr.<region>.amazonaws.com/rag-ingest:latest
     ```

3. Create or update Lambda functions to use the images or ZIP artifacts. Ensure the handler is set to `lambda_function.lambda_handler` if using the provided Dockerfiles (or awslambdaric with a ZIP package).

4. Create S3 bucket to hold user documents, and configure an S3 event notification to trigger the ingest Lambda on object creation. The ingest lambda relies on S3 object tagging for status updates.

5. Create a Cognito User Pool and App Client, then update frontend secrets with Cognito values so the Streamlit app can use Cognito for login.

6. Deploy Neo4j (AuraDB or self-hosted) and Pinecone index before running ingest.

7. Update Streamlit secrets with endpoints, e.g. `QUERY_LAMBDA_URL` (API Gateway or Lambda Function URL) to allow the frontend to call the query service.

> Note: This repository does not include pre-built CloudFormation or Terraform templates; please provision resources manually or with your preferred IaC.

---

## Configuration: Environment variables & Streamlit secrets

The repository contains `.env.example`. Below is the authoritative mapping. For local backend runs, the `.env` file is used by python-dotenv. For the Streamlit frontend, use `.streamlit/secrets.toml` or set environment variables in your hosting platform.

.env / st.secrets mapping (descriptions):

- AWS CONFIG
  - REGION_NAME / AWS_REGION: AWS region (e.g., us-east-1)
  - AWS_ACCESS_KEY_ID: AWS access key (do not commit)
  - AWS_SECRET_ACCESS_KEY: AWS secret key (do not commit)
  - S3_BUCKET_NAME: Bucket used for uploading documents and status tagging
  - COGNITO_USER_POOL_ID: Cognito user pool id for authentication
  - COGNITO_APP_CLIENT_ID: Cognito App Client ID for auth flows

- DATABASES
  - PINECONE_API_KEY: API key for Pinecone
  - PINECONE_INDEX_NAME: Pinecone index name used by the app
  - NEO4J_URI: Bolt or neo4j+s URL for Neo4j (e.g., neo4j+s://<host>)
  - NEO4J_USERNAME: Neo4j username
  - NEO4J_PASSWORD: Neo4j password
  - NEO4J_DATABASE: Optional target database name
  - AURA_INSTANCEID / AURA_INSTANCENAME: optional Aura fields

- AI MODEL (Google Gemini)
  - GOOGLE_API_KEY: Google API key for GenAI (Gemini) access

- FRONTEND / LAMBDA ENDPOINTS
  - QUERY_LAMBDA_URL: URL for query Lambda (API Gateway or Lambda Function URL)

Streamlit secrets example (`.streamlit/secrets.toml`):
```toml
AWS_REGION = "us-east-1"
AWS_ACCESS_KEY_ID = "AKIA..."
AWS_SECRET_ACCESS_KEY = "..."
S3_BUCKET_NAME = "your-rag-project-storage"
COGNITO_APP_CLIENT_ID = "..."
COGNITO_USER_POOL_ID = "..."
QUERY_LAMBDA_URL = "https://your-api-gateway-or-lambda-url"
PINECONE_API_KEY = "..."
PINECONE_INDEX_NAME = "..."
NEO4J_URI = "neo4j+s://..."
NEO4J_USERNAME = "..."
NEO4J_PASSWORD = "..."
GOOGLE_API_KEY = "..."
```

Important: Do not commit `.env` or `.streamlit/secrets.toml` to source control. Use secret storage (AWS Secrets Manager, Parameter Store, or CI/CD secret storage) for production.

---

## How it works: Implementation details

<!-- DIAGRAM: Ingest Pipeline Flow -->

Ingest pipeline (backend/ingest/ingest.py):
- Text extraction: pymupdf loads the PDF and extracts page text.
- Clean-up: `clean_scanned_text` applies regex fixes for hyphenated line breaks and surplus whitespace.
- Chunking: `recursive_split` splits into chunks (~1000 chars default with 100 overlap) using smart split heuristics (prefer periods/spaces).
- Embeddings: Sends batches of chunks to Google GenAI embedding model `gemini-embedding-001` via genai client.
- Pinecone upsert: Upserts vectors in batches of 50 into Pinecone index, using user email as namespace.
- Graph extraction: Generates a dense summary (Gemini), then extracts knowledge triples using a JSON schema. Converts triples into sanitized relationship types and persists them in Neo4j (MERGE semantics).
- Status updates: Tags the S3 object with status (`indexing`, `ready`, `failed`) via `put_object_tagging`.

<!-- DIAGRAM: Query Pipeline Flow -->

Query pipeline (backend/query/query.py):
- Embedding query: Uses GenAI to embed the user's question.
- Vector search: Queries Pinecone namespace (user space) for top_k matches (k=4), returns metadata text.
- Graph search: Uses Gemini to generate a Cypher query (the LLM writes the Cypher to find entities and related nodes).
- Aggregation: Combines vector and graph results into a context block, then calls Gemini to synthesize a final answer using a system instruction that forces it to use only the provided context.
- Response: Returns answer and references (vector chunks and graph facts).

<!-- DIAGRAM: Frontend User Flow -->

Frontend (Streamlit):
- Login/Registration using Cognito via frontend/auth_client.py.
- Uploads stored into S3 (per-user folder).
- Polling: The frontend polls S3 object tags to wait for ingestion completion (helper functions implemented in frontend/files_handler.py).
- Query: The frontend calls an endpoint (QUERY_LAMBDA_URL) to get answer and references. The UI displays answer and the cited contexts.

---

## Sample API request

If you have a query endpoint URL (`QUERY_LAMBDA_URL`), you can test it with curl:

```bash
curl -X POST $QUERY_LAMBDA_URL \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Who is Thomas Jefferson?",
    "user_email": "alice@example.com"
  }'
```

Successful response: JSON with `answer` and `references` (array of vector and graph results).

---

## Troubleshooting & diagnostics

Common problems and how to diagnose them:

- Authentication/permissions errors:
  - Errors when uploading to S3 from the frontend: verify `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in Streamlit secrets and ensure the IAM user has PutObject/GetObject/PutObjectTagging permissions for the S3 bucket.
  - Cognito sign-up / login errors: ensure the Cognito App Client ID and User Pool ID are correct and the app client authorizes USER_PASSWORD_AUTH if used.

- Pinecone / Neo4j connectivity:
  - Connection or timeout errors: confirm API keys, index names, and host URLs; check network egress and VPC settings (Lambda within private subnets must have NAT to reach external services).
  - Empty search results: ensure ingestion succeeded and vectors have been upserted to the expected namespace (user email). Check upsert logs in ingest Lambda.

- Google GenAI failures:
  - API key invalid or quota exceeded. Check the project associated with the key. Enable GenAI APIs where required.

- Memory or timeouts in Lambda:
  - Large PDFs can increase memory and runtime. Consider increasing Lambda memory/time or pre-chunking files.

- Debugging logs:
  - For Lambda: use CloudWatch logs. Look for prints and caught exceptions in ingest.py and query.py.
  - For local runs: the console prints details; run the backend Python files directly to see test outputs.

- S3 object tags used for ingestion status are critical to the frontend polling flow. If tags are not being updated, verify `s3:PutObjectTagging` permission for the ingest role.

---

## Security best practices

- Never commit secrets to Git. Use `.gitignore` (this repo has one) and secure secret storage (AWS Secrets Manager, Parameter Store, or CI/CD secret vaults).
- Least privilege IAM: grant only the permissions each service needs (S3 bucket access, Lambda execute, CloudWatch logs, etc.).
- Network controls: if Neo4j is hosted in a private network, deploy Lambdas inside a VPC with appropriate subnets and NAT gateway.
- Rotate and audit API keys regularly (Pinecone, Google GenAI, Neo4j).
- Input sanitization: the repo uses LLM-generated Cypher queries. In production, review and sanitize generated Cypher before executing or tightly constrain model prompts/response format.

---

## Contributing

- Please open issues and pull requests for bug fixes, features, or documentation improvements.
- Contributor workflow:
  1. Fork repository.
  2. Create a feature branch.
  3. Implement and test changes.
  4. Open a PR with a clear description and testing notes.

Before opening PRs that modify deployment scripts, coordinate to avoid interfering with shared resources.

---

## Useful commands summary

Install requirements:
- Frontend:
  ```bash
  python -m pip install -r frontend/requirements.txt
  ```
- Ingest:
  ```bash
  python -m pip install -r backend/ingest/ingest_requirements.txt
  ```
- Query:
  ```bash
  python -m pip install -r backend/query/query-requirements.txt
  ```

Run Streamlit:
```bash
streamlit run frontend/app.py
```

Run local backend tests:
```bash
python backend/ingest/ingest.py
python backend/query/query.py
```

Build Docker images:
```bash
docker build -t rag-ingest -f backend/ingest/Dockerfile .
docker build -t rag-query -f backend/query/Dockerfile .
```

Deploy scripts:
```bash
# Ensure executable
chmod +x scripts/*.sh
./scripts/deploy_all.sh
```

---

## License

This project is licensed under the Apache License 2.0. See the LICENSE file for details.