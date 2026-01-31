# RAG-on-AWS

Fully End-to-End serverless hybrid Retrieval-Augmented Generation (RAG) application designed to run on AWS. The system ingests PDF documents into two knowledge stores (a vector database (Pinecone) for dense retrieval and a knowledge graph (Neo4j) for structured facts), then serves a Streamlit frontend that queries both and synthesizes answers using Google GenAI (Gemini), served by Amazon Lambda functions.

![](./figures/architecture.svg)

## Tech Stack

* **Frontend:**
    ![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)

* **Backend:** 
    ![ECR][ECR-logo]
    ![AWS Lambda][Lambda-logo]
* **Authentication:** ![Cognito][Cognito-logo]

* **File Storage**: ![Amazon S3][S3-logo]

* **Vector Database:** ![Pinecone][Pinecone-logo]

* **Graph Database:** ![Neo4j](https://img.shields.io/badge/Neo4j-008CC1?logo=neo4j&logoColor=white)

* **Chat & Embedding Models:**
    ![Google Gemini](https://img.shields.io/badge/Google%20Gemini-8E75B2?logo=googlegemini&logoColor=white)

* **Source Control:**
    ![Git](https://img.shields.io/badge/git-%23F05033.svg?logo=git&logoColor=white)
    ![GitHub](https://img.shields.io/badge/github-%23121011.svg?logo=github&logoColor=white)

## Table of contents
- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Quickstart: Local development](#quickstart-local-development)
- [Run backend components locally (ingest & query)](#run-backend-components-locally)
- [Docker: Build the Lambda-compatible artifacts](#docker-build-the-lambda-compatible-artifacts)
- [Deploying to AWS](#deploying-to-aws)
- [Configuration: Environment variables & Streamlit secrets](#configuration-environment-variables--streamlit-secrets)
- [How it works: Implementation details](#how-it-works-implementation-details)
- [Troubleshooting & diagnostics](#troubleshooting--diagnostics)
- [Security best practices](#security-best-practices)
- [Contributing](#contributing)
- [License](#license)

---

## Project Overview

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

Project structure
```text
RAGwithAWS/
├── backend/                            
│   ├── ingest/                         # Ingest Lambda
│   │   ├── ingest.py
│   │   ├── ingest_requirements.txt
│   │   └── Dockerfile
│   └── query/                          # Query Lambda
│       ├── query.py
│       ├── query_requirements.txt
│       └── Dockerfile
├── frontend/                           # Streamlit frontend
│   ├── app.py                          # Landing page
│   ├── auth_client.py                  # Authentication
│   ├── chat_api.py                     # API call to query handler
│   ├── files_handler.py                # S3 file upload/delete
│   └── requirements.txt
├── infrastructure/                     # IaaC (coming soon)
│   └── main.tf                         
├── scripts/                            # Automation scripts
│   ├── deploy_all.sh
│   ├── deploy_ingest.sh
│   └── deploy_query.sh
├── .env.example 
├── .gitignore 
├── LICENSE
└── README.md
```

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

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

<!-- Logos and Icons -->

[ECR-logo]:https://img.shields.io/badge/ECR-27272A?logo=data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPHN2ZyB3aWR0aD0iODBweCIgaGVpZ2h0PSI4MHB4IiB2aWV3Qm94PSIwIDAgODAgODAiIHZlcnNpb249IjEuMSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIiB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayI+CiAgICA8IS0tIEdlbmVyYXRvcjogU2tldGNoIDY0ICg5MzUzNykgLSBodHRwczovL3NrZXRjaC5jb20gLS0+CiAgICA8dGl0bGU+SWNvbi1BcmNoaXRlY3R1cmUvNjQvQXJjaF9BbWF6b24tRWxhc3RpYy1Db250YWluZXItUmVnaXN0cnlfNjQ8L3RpdGxlPgogICAgPGRlc2M+Q3JlYXRlZCB3aXRoIFNrZXRjaC48L2Rlc2M+CiAgICA8ZGVmcz4KICAgICAgICA8bGluZWFyR3JhZGllbnQgeDE9IjAlIiB5MT0iMTAwJSIgeDI9IjEwMCUiIHkyPSIwJSIgaWQ9ImxpbmVhckdyYWRpZW50LTEiPgogICAgICAgICAgICA8c3RvcCBzdG9wLWNvbG9yPSIjQzg1MTFCIiBvZmZzZXQ9IjAlIj48L3N0b3A+CiAgICAgICAgICAgIDxzdG9wIHN0b3AtY29sb3I9IiNGRjk5MDAiIG9mZnNldD0iMTAwJSI+PC9zdG9wPgogICAgICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8L2RlZnM+CiAgICA8ZyBpZD0iSWNvbi1BcmNoaXRlY3R1cmUvNjQvQXJjaF9BbWF6b24tRWxhc3RpYy1Db250YWluZXItUmVnaXN0cnlfNjQiIHN0cm9rZT0ibm9uZSIgc3Ryb2tlLXdpZHRoPSIxIiBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPgogICAgICAgIDxnIGlkPSJJY29uLUFyY2hpdGVjdHVyZS1CRy82NC9Db250YWluZXJzIiBmaWxsPSJ1cmwoI2xpbmVhckdyYWRpZW50LTEpIj4KICAgICAgICAgICAgPHJlY3QgaWQ9IlJlY3RhbmdsZSIgeD0iMCIgeT0iMCIgd2lkdGg9IjgwIiBoZWlnaHQ9IjgwIj48L3JlY3Q+CiAgICAgICAgPC9nPgogICAgICAgIDxwYXRoIGQ9Ik0zOC43ODgwNzQxLDM3LjU3NzY5NDUgQzM4LjI5MzM4NDUsMzcuODY1NTEyNSAzNy45ODU1Nzc3LDM4LjQwMDAzMTcgMzcuOTg1NTc3NywzOC45NzM2NjIgTDM3Ljk4NTU3NzcsNjYuNzE5NTE4NiBMMTYuOTk4NzQ1OSw1NC45ODQxNjU1IEwxNi45OTg3NDU5LDI3LjcwNzY0MjggTDQwLjU1Njk2NDMsMTQuMDU4ODUxNSBMNjEuNDg0ODMzLDI0LjQyODMyMjYgTDM4Ljc4ODA3NDEsMzcuNTc3Njk0NSBaIE02My45MjAzMDQ5LDI0LjQwMjI0ODUgQzYzLjkyMDMwNDksMjMuODI3NjE1MyA2My42MTM0OTc0LDIzLjI5MjA5MzMgNjMuMDU5ODQ0OCwyMi45NzUxOTI3IEw0MS4zNDY0Njg5LDEyLjIxNDYwOTkgQzQwLjg1MDc3OTksMTEuOTI4Nzk3NiA0MC4yMzUxNjYyLDExLjkyNzc5NDggMzkuNzQwNDc2NiwxMi4yMTU2MTI4IEwxNS44MDI0OTY1LDI2LjA4NDAyODMgQzE1LjMwNzgwNjksMjYuMzcxODQ2MyAxNSwyNi45MDYzNjU1IDE1LDI3LjQ3OTk5NTggTDE1LDU1LjIxNTgyMzkgQzE1LDU1Ljc4OTQ1NDIgMTUuMzA3ODA2OSw1Ni4zMjM5NzM0IDE1LjgxNzQ4NzEsNTYuNjE5ODE0MiBMMzcuNTczODM2LDY4Ljc4NTM5MDEgQzM3LjgyMTY4MDUsNjguOTI4Nzk3NiAzOC4xMDA1MDU2LDY5IDM4LjM3ODMzMTIsNjkgQzM4LjY1NTE1NzUsNjkgMzguOTMzOTgyNiw2OC45Mjg3OTc2IDM5LjE4MDgyNzcsNjguNzg1MzkwMSBDMzkuNjc2NTE2Nyw2OC40OTg1NzQ5IDM5Ljk4NDMyMzYsNjcuOTY0MDU1NyAzOS45ODQzMjM2LDY3LjM4OTQyMjYgTDM5Ljk4NDMyMzYsMzkuMjAxMzA5IEw2My4xMTc4MDg0LDI1Ljc5ODIxNiBDNjMuNjEzNDk3NCwyNS41MTE0MDA4IDYzLjkyMDMwNDksMjQuOTc2ODgxNyA2My45MjAzMDQ5LDI0LjQwMjI0ODUgTDYzLjkyMDMwNDksMjQuNDAyMjQ4NSBaIE02My45NjkyNzQyLDU1LjA0NzM0NTEgTDQ0Ljk4MTE4ODMsNjYuNjYxMzUzMyBMNDQuOTgxMTg4Myw1Ni4yNjE3OTY3IEw1NC44ODE5NzYsNDkuODcyNjM4IEw1NC45NDk5MzM0LDQ5LjQyNDM2NCBDNTQuOTY3OTIyMSw0OS4zMDcwMzA1IDU0Ljk3NDkxNzcsNDkuMzA3MDMwNSA1NC45NzQ5MTc3LDQ4Ljc2NjQ5NDIgTDU1LjAwNTg5ODMsMzYuMzYwMjM0NCBMNjQuMDAwMjU0NywzMS4xNDg0MjE4IEw2My45NjkyNzQyLDU1LjA0NzM0NTEgWiBNNjUuMTk2NTA0MiwyOS4wNzE1MTkxIEM2NC42OTk4MTU4LDI4Ljc4MTY5NTMgNjQuMDg0MjAyMSwyOC43ODI2OTgyIDYzLjU4ODUxMzEsMjkuMDcxNTE5MSBMNTQuMDEzNTIwOSwzNC42MTgyODM1IEM1My43MTM3MDksMzQuNzgxNzQ4MSA1My4wMDgxNTE3LDM1LjE2NTgzOTggNTMuMDA4MTUxNywzNS45NTgwOTE0IEw1Mi45NzYxNzE4LDQ4LjcxNzM1NDYgTDQzLjg1MDg5NzUsNTQuNjA2MDkxIEM0My4zMDYyMzkyLDU0LjkzMTAxNDUgNDIuOTgyNDQyNCw1NS40NDU0NzY2IDQyLjk4MjQ0MjQsNTUuOTg5MDIxNCBMNDIuOTgyNDQyNCw2Ny4zMDgxOTE3IEM0Mi45ODI0NDI0LDY3Ljg3NDgwMjEgNDMuMjg3MjUxMSw2OC4zOTEyNjk5IDQzLjc5NzkzMDcsNjguNjg3MTEwNyBDNDQuMDY0NzYzMyw2OC44NDA1NDY4IDQ0LjM2MTU3Nyw2OC45MTg3NjkxIDQ0LjY1NzM5MTQsNjguOTE4NzY5MSBDNDQuOTQ4MjA5LDY4LjkxODc2OTEgNDUuMjM5MDI2NSw2OC44NDQ1NTgyIDQ1LjUwMTg2MTYsNjguNjkyMTI1IEw2NS4xNjc1MjIzLDU2LjY2MzkzOTYgQzY1LjY2MjIxMTksNTYuMzc2MTIxNiA2NS45NjgwMjAxLDU1Ljg0MTYwMjQgNjUuOTY4MDIwMSw1NS4yNzA5ODA3IEw2NiwzMC40NjY0ODM3IEM2NiwyOS44OTI4NTM0IDY1LjY5MjE5MzEsMjkuMzU4MzM0MiA2NS4xOTY1MDQyLDI5LjA3MTUxOTEgTDY1LjE5NjUwNDIsMjkuMDcxNTE5MSBaIiBpZD0iQW1hem9uLUVsYXN0aWMtQ29udGFpbmVyLVJlZ2lzdHJ5X0ljb25fNjRfU3F1aWQiIGZpbGw9IiNGRkZGRkYiPjwvcGF0aD4KICAgIDwvZz4KPC9zdmc+

[Lambda-logo]:https://img.shields.io/badge/Lambda-27272A?logo=data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPHN2ZyB3aWR0aD0iODBweCIgaGVpZ2h0PSI4MHB4IiB2aWV3Qm94PSIwIDAgODAgODAiIHZlcnNpb249IjEuMSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIiB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayI+CiAgICA8IS0tIEdlbmVyYXRvcjogU2tldGNoIDY0ICg5MzUzNykgLSBodHRwczovL3NrZXRjaC5jb20gLS0+CiAgICA8dGl0bGU+SWNvbi1BcmNoaXRlY3R1cmUvNjQvQXJjaF9BV1MtTGFtYmRhXzY0PC90aXRsZT4KICAgIDxkZXNjPkNyZWF0ZWQgd2l0aCBTa2V0Y2guPC9kZXNjPgogICAgPGRlZnM+CiAgICAgICAgPGxpbmVhckdyYWRpZW50IHgxPSIwJSIgeTE9IjEwMCUiIHgyPSIxMDAlIiB5Mj0iMCUiIGlkPSJsaW5lYXJHcmFkaWVudC0xIj4KICAgICAgICAgICAgPHN0b3Agc3RvcC1jb2xvcj0iI0M4NTExQiIgb2Zmc2V0PSIwJSI+PC9zdG9wPgogICAgICAgICAgICA8c3RvcCBzdG9wLWNvbG9yPSIjRkY5OTAwIiBvZmZzZXQ9IjEwMCUiPjwvc3RvcD4KICAgICAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPC9kZWZzPgogICAgPGcgaWQ9Ikljb24tQXJjaGl0ZWN0dXJlLzY0L0FyY2hfQVdTLUxhbWJkYV82NCIgc3Ryb2tlPSJub25lIiBzdHJva2Utd2lkdGg9IjEiIGZpbGw9Im5vbmUiIGZpbGwtcnVsZT0iZXZlbm9kZCI+CiAgICAgICAgPGcgaWQ9Ikljb24tQXJjaGl0ZWN0dXJlLUJHLzY0L0NvbXB1dGUiIGZpbGw9InVybCgjbGluZWFyR3JhZGllbnQtMSkiPgogICAgICAgICAgICA8cmVjdCBpZD0iUmVjdGFuZ2xlIiB4PSIwIiB5PSIwIiB3aWR0aD0iODAiIGhlaWdodD0iODAiPjwvcmVjdD4KICAgICAgICA8L2c+CiAgICAgICAgPHBhdGggZD0iTTI4LjAwNzUzNTIsNjYgTDE1LjU5MDcyNzQsNjYgTDI5LjMyMzU4ODUsMzcuMjk2IEwzNS41NDYwMjQ5LDUwLjEwNiBMMjguMDA3NTM1Miw2NiBaIE0zMC4yMTk2Njc0LDM0LjU1MyBDMzAuMDUxMjc2OCwzNC4yMDggMjkuNzAwNDYyOSwzMy45ODkgMjkuMzE3NTc0NSwzMy45ODkgTDI5LjMxNDU2NzYsMzMuOTg5IEMyOC45Mjg2NzIzLDMzLjk5IDI4LjU3Nzg1ODMsMzQuMjExIDI4LjQxMjQ3NDYsMzQuNTU4IEwxMy4wOTc5NDQsNjYuNTY5IEMxMi45NDk1OTk5LDY2Ljg3OSAxMi45NzA2NDg3LDY3LjI0MyAxMy4xNTUwNzY2LDY3LjUzNCBDMTMuMzM3NDk5OCw2Ny44MjQgMTMuNjU4MjQzOSw2OCAxNC4wMDIwNDE2LDY4IEwyOC42NDIwMDcyLDY4IEMyOS4wMjk5MDcxLDY4IDI5LjM4MTcyMzQsNjcuNzc3IDI5LjU0ODEwOTQsNjcuNDI4IEwzNy41NjM3MDYsNTAuNTI4IEMzNy42OTMwMDYsNTAuMjU0IDM3LjY5MjAwMzcsNDkuOTM3IDM3LjU1ODY5NDQsNDkuNjY1IEwzMC4yMTk2Njc0LDM0LjU1MyBaIE02NC45OTUzNDkxLDY2IEw1Mi42NTg3Mjc0LDY2IEwzMi44NjY4MDksMjQuNTcgQzMyLjcwMTQyNTMsMjQuMjIyIDMyLjM0ODYwNjcsMjQgMzEuOTYxNzA5MSwyNCBMMjMuODg5OTgyMiwyNCBMMjMuODk5MDAzMSwxNCBMMzkuNzE5NzA4MSwxNCBMNTkuNDIwNDE0OSw1NS40MjkgQzU5LjU4NTc5ODYsNTUuNzc3IDU5LjkzODYxNzIsNTYgNjAuMzI1NTE0OCw1NiBMNjQuOTk1MzQ5MSw1NiBMNjQuOTk1MzQ5MSw2NiBaIE02NS45OTc2NzQ1LDU0IEw2MC45NTk5ODY4LDU0IEw0MS4yNTkyOCwxMi41NzEgQzQxLjA5Mzg5NjMsMTIuMjIzIDQwLjc0MTA3NzcsMTIgNDAuMzUzMTc3OCwxMiBMMjIuODk3NjgsMTIgQzIyLjM0NTM5ODcsMTIgMjEuODk2MzU2OSwxMi40NDcgMjEuODk1MzU0NSwxMi45OTkgTDIxLjg4NDMyOSwyNC45OTkgQzIxLjg4NDMyOSwyNS4yNjUgMjEuOTg4NTcwOCwyNS41MTkgMjIuMTc4MDEwMywyNS43MDcgQzIyLjM2NTQ0NTIsMjUuODk1IDIyLjYyMDAzNTgsMjYgMjIuODg2NjU0NCwyNiBMMzEuMzI5MjQxNywyNiBMNTEuMTIyMTYyNSw2Ny40MyBDNTEuMjg4NTQ4NSw2Ny43NzggNTEuNjM5MzYyNCw2OCA1Mi4wMjYyNiw2OCBMNjUuOTk3Njc0NSw2OCBDNjYuNTUxOTYwNSw2OCA2Nyw2Ny41NTIgNjcsNjcgTDY3LDU1IEM2Nyw1NC40NDggNjYuNTUxOTYwNSw1NCA2NS45OTc2NzQ1LDU0IEw2NS45OTc2NzQ1LDU0IFoiIGlkPSJBV1MtTGFtYmRhX0ljb25fNjRfU3F1aWQiIGZpbGw9IiNGRkZGRkYiPjwvcGF0aD4KICAgIDwvZz4KPC9zdmc+

[S3-logo]: https://img.shields.io/badge/S3-27272A?logo=data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPHN2ZyB3aWR0aD0iODBweCIgaGVpZ2h0PSI4MHB4IiB2aWV3Qm94PSIwIDAgODAgODAiIHZlcnNpb249IjEuMSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIiB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayI+CiAgICA8dGl0bGU+SWNvbi1BcmNoaXRlY3R1cmUvNjQvQXJjaF9BbWF6b24tU2ltcGxlLVN0b3JhZ2UtU2VydmljZV82NDwvdGl0bGU+CiAgICA8ZGVmcz4KICAgICAgICA8bGluZWFyR3JhZGllbnQgeDE9IjAlIiB5MT0iMTAwJSIgeDI9IjEwMCUiIHkyPSIwJSIgaWQ9ImxpbmVhckdyYWRpZW50LTEiPgogICAgICAgICAgICA8c3RvcCBzdG9wLWNvbG9yPSIjMUI2NjBGIiBvZmZzZXQ9IjAlIj48L3N0b3A+CiAgICAgICAgICAgIDxzdG9wIHN0b3AtY29sb3I9IiM2Q0FFM0UiIG9mZnNldD0iMTAwJSI+PC9zdG9wPgogICAgICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8L2RlZnM+CiAgICA8ZyBpZD0iSWNvbi1BcmNoaXRlY3R1cmUvNjQvQXJjaF9BbWF6b24tU2ltcGxlLVN0b3JhZ2UtU2VydmljZV82NCIgc3Ryb2tlPSJub25lIiBzdHJva2Utd2lkdGg9IjEiIGZpbGw9Im5vbmUiIGZpbGwtcnVsZT0iZXZlbm9kZCI+CiAgICAgICAgPGcgaWQ9IlJlY3RhbmdsZSIgZmlsbD0idXJsKCNsaW5lYXJHcmFkaWVudC0xKSI+CiAgICAgICAgICAgIDxyZWN0IHg9IjAiIHk9IjAiIHdpZHRoPSI4MCIgaGVpZ2h0PSI4MCI+PC9yZWN0PgogICAgICAgIDwvZz4KICAgICAgICA8ZyBpZD0iSWNvbi1TZXJ2aWNlLzY0L0FtYXpvbi1TaW1wbGUtU3RvcmFnZS1TZXJ2aWNlXzY0IiB0cmFuc2Zvcm09InRyYW5zbGF0ZSg4LjAwMDAwMCwgOC4wMDAwMDApIiBmaWxsPSIjRkZGRkZGIj4KICAgICAgICAgICAgPHBhdGggZD0iTTUyLjgzNTksMzQuODkyNiBMNTMuMjE5OSwzMi4xODg2IEM1Ni43NjA5LDM0LjMwOTYgNTYuODA2OSwzNS4xODU2IDU2LjgwNTkxMzIsMzUuMjA5NiBDNTYuNzk5OSwzNS4yMTQ2IDU2LjE5NTksMzUuNzE4NiA1Mi44MzU5LDM0Ljg5MjYgTDUyLjgzNTksMzQuODkyNiBaIE01MC44OTI5LDM0LjM1MjYgQzQ0Ljc3MjksMzIuNTAwNiAzNi4yNDk5LDI4LjU5MDYgMzIuODAwOSwyNi45NjA2IEMzMi44MDA5LDI2Ljk0NjYgMzIuODA0OSwyNi45MzM2IDMyLjgwNDksMjYuOTE5NiBDMzIuODA0OSwyNS41OTQ2IDMxLjcyNjksMjQuNTE2NiAzMC40MDA5LDI0LjUxNjYgQzI5LjA3NjksMjQuNTE2NiAyNy45OTg5LDI1LjU5NDYgMjcuOTk4OSwyNi45MTk2IEMyNy45OTg5LDI4LjI0NDYgMjkuMDc2OSwyOS4zMjI2IDMwLjQwMDksMjkuMzIyNiBDMzAuOTgyOSwyOS4zMjI2IDMxLjUxMDksMjkuMTA1NiAzMS45Mjc5LDI4Ljc2MDYgQzM1Ljk4NTksMzAuNjgxNiA0NC40NDI5LDM0LjUzNDYgNTAuNjA3OSwzNi4zNTQ2IEw0OC4xNjk5LDUzLjU2MDYgQzQ4LjE2MjksNTMuNjA3NiA0OC4xNTk5LDUzLjY1NDYgNDguMTU5OSw1My43MDE2IEM0OC4xNTk5LDU1LjIxNjYgNDEuNDUyOSw1Ny45OTk2IDMwLjQ5MzksNTcuOTk5NiBDMTkuNDE4OSw1Ny45OTk2IDEyLjY0MDksNTUuMjE2NiAxMi42NDA5LDUzLjcwMTYgQzEyLjY0MDksNTMuNjU1NiAxMi42Mzc5LDUzLjYxMDYgMTIuNjMxOSw1My41NjU2IEw3LjUzNzksMTYuMzU4NiBDMTEuOTQ2OSwxOS4zOTM2IDIxLjQyOTksMjAuOTk5NiAzMC40OTk5LDIwLjk5OTYgQzM5LjU1NTksMjAuOTk5NiA0OS4wMjI5LDE5LjM5OTYgNTMuNDQwOSwxNi4zNzM2IEw1MC44OTI5LDM0LjM1MjYgWiBNNi45OTk5LDEyLjQ3NzYgQzcuMDcxOSwxMS4xNjE2IDE0LjYzMzksNS45OTk2IDMwLjQ5OTksNS45OTk2IEM0Ni4zNjM5LDUuOTk5NiA1My45MjY5LDExLjE2MDYgNTMuOTk5OSwxMi40Nzc2IEw1My45OTk5LDEyLjkyNjYgQzUzLjEyOTksMTUuODc3NiA0My4zMjk5LDE4Ljk5OTYgMzAuNDk5OSwxOC45OTk2IEMxNy42NDc5LDE4Ljk5OTYgNy44NDI5LDE1Ljg2NzYgNi45OTk5LDEyLjkxMjYgTDYuOTk5OSwxMi40Nzc2IFogTTU1Ljk5OTksMTIuNDk5NiBDNTUuOTk5OSw5LjAzNDYgNDYuMDY1OSwzLjk5OTYgMzAuNDk5OSwzLjk5OTYgQzE0LjkzMzksMy45OTk2IDQuOTk5OSw5LjAzNDYgNC45OTk5LDEyLjQ5OTYgTDUuMDkzOSwxMy4yNTM2IEwxMC42NDE5LDUzLjc3NzYgQzEwLjc3NDksNTguMzA5NiAyMi44NjA5LDU5Ljk5OTYgMzAuNDkzOSw1OS45OTk2IEMzOS45NjU5LDU5Ljk5OTYgNTAuMDI4OSw1Ny44MjE2IDUwLjE1ODksNTMuNzgwNiBMNTIuNTU0OSwzNi44ODM2IEM1My44ODc5LDM3LjIwMjYgNTQuOTg0OSwzNy4zNjU2IDU1Ljg2NTksMzcuMzY1NiBDNTcuMDQ4OSwzNy4zNjU2IDU3Ljg0ODksMzcuMDc2NiA1OC4zMzM5LDM2LjQ5ODYgQzU4LjczMTksMzYuMDI0NiA1OC44ODM5LDM1LjQ1MDYgNTguNzY5OSwzNC44Mzk2IEM1OC41MTA5LDMzLjQ1NTYgNTYuODY3OSwzMS45NjM2IDUzLjUyMTksMzAuMDU0NiBMNTUuODk3OSwxMy4yOTI2IEw1NS45OTk5LDEyLjQ5OTYgWiIgaWQ9IkFtYXpvbi1TaW1wbGUtU3RvcmFnZS1TZXJ2aWNlLUljb25fNjRfU3F1aWQiPjwvcGF0aD4KICAgICAgICA8L2c+CiAgICA8L2c+Cjwvc3ZnPg==

[Pinecone-logo]: https://img.shields.io/badge/Pinecone-FFFFFF?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGZpbGw9Im5vbmUiIHZpZXdCb3g9IjAgMCAyNCAyNCIgaWQ9IlBpbmVjb25lLUljb24tLVN0cmVhbWxpbmUtU3ZnLUxvZ29zIiBoZWlnaHQ9IjI0IiB3aWR0aD0iMjQiPgogIDxkZXNjPgogICAgUGluZWNvbmUgSWNvbiBTdHJlYW1saW5lIEljb246IGh0dHBzOi8vc3RyZWFtbGluZWhxLmNvbQogIDwvZGVzYz4KICA8cGF0aCBmaWxsPSIjMjAxZDFlIiBkPSJNMTAuNDE1OTc1IDIxLjA2MDUyNWMwLjc0MjY3NSAwIDEuMzQ0NzUgMC42MDIwNSAxLjM0NDc1IDEuMzQ0NzI1IDAgMC43NDI3IC0wLjYwMjA3NSAxLjM0NDc1IC0xLjM0NDc1IDEuMzQ0NzUgLTAuNzQyNjc1IDAgLTEuMzQ0NzI1IC0wLjYwMjA1IC0xLjM0NDcyNSAtMS4zNDQ3NSAwIC0wLjc0MjY3NSAwLjYwMjA1IC0xLjM0NDcyNSAxLjM0NDcyNSAtMS4zNDQ3MjVabTcuNDYwNjI1IC0yLjQ1MzU1IDEuMzI4ODc1IDAuMzkzNzI1IC0xLjA1NDg1IDMuNTYwMTc1Yy0wLjA5MjE3NSAwLjMxMTEgLTAuMzg3ODUgMC41MTY1NzUgLTAuNzExNTUgMC40OTQ1MjVsLTAuMzI1ODI1IC0wLjAyMjM1IC0wLjAwNzk3NSAwLjAwNjU3NSAtMy4zODUzMjUgLTAuMjM3NTc1IDAuMDk0MiAtMS4zODI3NzUgMi4yNzQ0NSAwLjE1NDM1IC0xLjQ4OTAyNSAtMi4xNDggMS4xMzkwMjUgLTAuNzg5NyAxLjQ5MDk3NSAyLjE1MDY1IDAuNjQ3MDI1IC0yLjE3OTZabS0xNC40NjM2MjUgLTIuNDYxMTUgMS4zODI1MjUgMC4wOTc5MjUgLTAuMTYxOTI1IDIuMjc0MSAyLjE0NDA3NSAtMS40OTA5MjUgMC43OTE0NzUgMS4xMzc3NSAtMi4xNDY4NzUgMS40OTI1IDIuMTkxMzUgMC42NDU3IC0wLjM5MTcgMS4zMjk0NzUgLTMuNTc2OTc1IC0xLjA1MzgyNWMtMC4zMTIyNzUgLTAuMDkyIC0wLjUxODQyNSAtMC4zODg5NzUgLTAuNDk1NCAtMC43MTM3MjVsMC4yNjM0NSAtMy43MTg5NzVabTguOTI2NTI1IC0xLjkzNjUgMi40OTUyMjUgMy4wMTI1MjUgLTEuMTI0NTc1IDAuOTMxNDc1IC0xLjQ4NSAtMS43OTI4NSAtMC40ODE0MjUgMi43NTY1IC0xLjQzODQ1IC0wLjI1MTQ1IDAuNDgxOTI1IC0yLjc2MDc3NSAtMS45OTkxNzUgMS4xNzg3MjUgLTAuNzQxMiAtMS4yNTgxNSAzLjM1OTggLTEuOTc5MzI1YzAuMzA4ODc1IC0wLjE4MTk3NSAwLjcwNDIgLTAuMTEyNzc1IDAuOTMyODc1IDAuMTYzMzI1Wm02Ljk4MTEgLTIuMDIxMTUgMS4yNDY0NSAtMC42NzgxNSAxLjgxNTgyNSAzLjMzNzQ1YzAuMTU5MDc1IDAuMjkyMzc1IDAuMDkzNTI1IDAuNjU2IC0wLjE1NzYyNSAwLjg3NDQyNWwtMC4yNTY5IDAuMjIxOTc1IC0yLjYyMTQyNSAyLjI4MTM3NSAtMC45MzEyIC0xLjA3MDcgMS43NjIzNzUgLTEuNTMzMjUgLTIuNjI1MDc1IC0wLjQ3MjkyNSAwLjI1MTgyNSAtMS4zOTY0NSAyLjYyMzIyNSAwLjQ3MjY1IC0xLjEwNzQ3NSAtMi4wMzY0Wk00LjYyMSA4LjY5ODkyNWwwLjkzODk1IDEuMDYzOSAtMS43MzgxNzUgMS41MzMwMjUgMi42MzAwNzUgMC40NTkxNzUgLTAuMjQzNzc1IDEuMzk3OSAtMi42MzI5NzUgLTAuNDU5NTUgMS4xMzA5NSAyLjA0NDU3NSAtMS4yNDE2NzUgMC42ODY4NzUgLTEuODQ0OTIgLTMuMzM1MDVjLTAuMTYxMDggLTAuMjkxMTc1IC0wLjA5ODE0NSAtMC42NTUyIDAuMTUxMzUyNSAtMC44NzU0TDQuNjIxIDguNjk4OTI1Wm04Ljg5MDE1IC0xLjA5NzYgMi40ODY3NzUgMy4wMDQ0MjUgLTEuMTI0ODc1IDAuOTMxMDc1IC0xLjQ4NDY1IC0xLjc5MzYyNSAtMC40ODE0NSAyLjc1NzMyNSAtMS40Mzg0MjUgLTAuMjUxNDUgMC40ODAyNSAtMi43NTAwNzUgLTEuOTkxNSAxLjE2NzQ1IC0wLjczODM3NSAtMS4yNTk4MjUgMy4wNTkwNSAtMS43OTM1NSAwLjAwMzAyNSAtMC4wMTE2NSAwLjAxMzQ3NSAwLjAwMTc1IDAuMjg1MDc1IC0wLjE2NjIyNWMwLjMwODg1IC0wLjE4MSAwLjcwMzM3NSAtMC4xMTE0IDAuOTMxNjI1IDAuMTY0Mzc1Wm0zLjIwNDUyNSAtMS40Nzc1NzUgMC41NDM4NzUgLTEuMzEwNjI1IDMuNTE4MDUgMS40NTk5MjVjMC4zMDcwNSAwLjEyNzQyNSAwLjQ4NDQ3NSAwLjQ1MSAwLjQyNjggMC43Nzg0bC0wLjA1ODU3NSAwLjMyNTY3NSAtMC42MDA3NSAzLjQxNzMgLTEuMzk3NDc1IC0wLjI0NjE3NSAwLjQwMjY3NSAtMi4yODc1NSAtMi4zMzQgMS4yODk5NSAtMC42ODU5IC0xLjI0MjIgMi4zMzg0NzUgLTEuMjkxMDI1IC0yLjE1MzE3NSAtMC44OTM2NzVaTTEwLjAxMzg1IDMuNTQxMDVsMC4wNjA0NzUgMS40MTc3IC0yLjMyMzkyNSAwLjA5OTMyNSAxLjc1Mjc1IDIuMDAzMDI1IC0xLjA2NzkgMC45MzQ0MjUgLTEuNzU1NyAtMi4wMDYwNSAtMC40MDkwNSAyLjI5MDIyNSAtMS4zOTY4MjUgLTAuMjQ5ODUgMC42Njk0MjUgLTMuNzQyNjI1YzAuMDU4NSAtMC4zMjcxIDAuMzM2MTc1IC0wLjU2OTc3NSAwLjY2ODE3NSAtMC41ODM5NWwwLjMyODg1IC0wLjAxNDcgMC4wMDczNzUgLTAuMDA1MzUgMy40NjYzNSAtMC4xNDIxNzVaTTE0Ljc2NzYyNSAwLjUxNzYxNSAxNy4yNDMxNSAzLjU0MWwtMS4xMjk4MjUgMC45MjUxIC0xLjQ2OTI3NSAtMS43OTQ3NSAtMC40OTU1NzUgMi43NTM2NzUgLTEuNDM3MTUgLTAuMjU4NjI1IDAuNDk2NCAtMi43NTk4NjUgLTIuMDA2MDI1IDEuMTcyODY1IC0wLjczNjcyNSAtMS4yNjA3Nzc1TDEzLjgzNDM1IDAuMzQ5Nzc1YzAuMzEwMDI1IC0wLjE4MTE2Njc1IDAuNzA1Nzc1IC0wLjEwOTk5NTUgMC45MzMyNzUgMC4xNjc4NFoiIHN0cm9rZS13aWR0aD0iMC4yNSI+PC9wYXRoPgo8L3N2Zz4=

[Cognito-logo]: https://img.shields.io/badge/Amazon%20Cognito-27272A?logo=data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPHN2ZyB3aWR0aD0iODBweCIgaGVpZ2h0PSI4MHB4IiB2aWV3Qm94PSIwIDAgODAgODAiIHZlcnNpb249IjEuMSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIiB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayI+CiAgICA8IS0tIEdlbmVyYXRvcjogU2tldGNoIDY0ICg5MzUzNykgLSBodHRwczovL3NrZXRjaC5jb20gLS0+CiAgICA8dGl0bGU+SWNvbi1BcmNoaXRlY3R1cmUvNjQvQXJjaF9BbWF6b24tQ29nbml0b182NDwvdGl0bGU+CiAgICA8ZGVzYz5DcmVhdGVkIHdpdGggU2tldGNoLjwvZGVzYz4KICAgIDxkZWZzPgogICAgICAgIDxsaW5lYXJHcmFkaWVudCB4MT0iMCUiIHkxPSIxMDAlIiB4Mj0iMTAwJSIgeTI9IjAlIiBpZD0ibGluZWFyR3JhZGllbnQtMSI+CiAgICAgICAgICAgIDxzdG9wIHN0b3AtY29sb3I9IiNCRDA4MTYiIG9mZnNldD0iMCUiPjwvc3RvcD4KICAgICAgICAgICAgPHN0b3Agc3RvcC1jb2xvcj0iI0ZGNTI1MiIgb2Zmc2V0PSIxMDAlIj48L3N0b3A+CiAgICAgICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDwvZGVmcz4KICAgIDxnIGlkPSJJY29uLUFyY2hpdGVjdHVyZS82NC9BcmNoX0FtYXpvbi1Db2duaXRvXzY0IiBzdHJva2U9Im5vbmUiIHN0cm9rZS13aWR0aD0iMSIgZmlsbD0ibm9uZSIgZmlsbC1ydWxlPSJldmVub2RkIj4KICAgICAgICA8ZyBpZD0iSWNvbi1BcmNoaXRlY3R1cmUtQkcvNjQvU2VjdXJpdHktSWRlbnRpdHktQ29tcGxpYW5jZSIgZmlsbD0idXJsKCNsaW5lYXJHcmFkaWVudC0xKSI+CiAgICAgICAgICAgIDxyZWN0IGlkPSJSZWN0YW5nbGUiIHg9IjAiIHk9IjAiIHdpZHRoPSI4MCIgaGVpZ2h0PSI4MCI+PC9yZWN0PgogICAgICAgIDwvZz4KICAgICAgICA8cGF0aCBkPSJNMTYuOTYzNTYwOSwzNS44MDc5MjI1IEwyOS44Njg4MTkyLDM1LjgwNzkyMjUgTDI5Ljg2ODgxOTIsMzMuODI1Mzg0MSBMMTYuOTYzNTYwOSwzMy44MjUzODQxIEwxNi45NjM1NjA5LDM1LjgwNzkyMjUgWiBNNjEuMzc1NTE4Myw1MC4yMzA4ODk1IEw2Mi43NzkyMTMzLDUxLjYzMjU0NDEgTDU1LjQwNzMzMjcsNTguOTkzNzA5MyBDNTUuMjEyNzYxMSw1OS4xODcwMDY3IDU0Ljk1ODYyNjgsNTkuMjg0MTUxMSA1NC43MDU0ODUyLDU5LjI4NDE1MTEgQzU0LjQ1MTM1MDksNTkuMjg0MTUxMSA1NC4xOTcyMTY2LDU5LjE4NzAwNjcgNTQuMDAzNjM3Nyw1OC45OTM3MDkzIEw1MC4yOTQ4NjUsNTUuMjkxMzE4OCBMNTEuNjk4NTYsNTMuODg5NjY0MSBMNTQuNzA1NDg1Miw1Ni44OTEyMjczIEw2MS4zNzU1MTgzLDUwLjIzMDg4OTUgWiBNNjUuOTQzOTc5OCw1NS42OTM3NzQxIEM2NS43MTc2NDE0LDU3LjU1NzM2MDIgNjQuOTU5MjA5Myw1OS4yOTEwOSA2My43NDcxMDc3LDYwLjcwODYwNSBDNjIuODg2NDI2Miw2MS43MTU3MzQ1IDYxLjc5OTQwNjQsNjIuNTQ4NDAwNiA2MC42MDQxODEsNjMuMTE1NDA2NiBDNTkuMDAwOTUwOCw2My44NzU3MTAxIDU3LjIyMDAyNTEsNjQuMTY0MTY5NCA1NS40NDYwNDg1LDYzLjk0ODA3MjcgQzUzLjcyMDcxNDcsNjMuNzM3OTIzNyA1Mi4wOTQ2NTIyLDYzLjA1NzkxMyA1MC43Mzk2LDYxLjk4MjM4NTkgQzQ4LjEzNjcwODcsNTkuOTE1NTg5NiA0Ni44MjIzNTc4LDU2LjcxMDgxNjMgNDcuMjIyNDIwOCw1My40MDg4OTg1IEM0Ny42MDA2NDQxLDUwLjI4ODM4MzEgNDkuNDkxNzYwOCw0Ny41NjYzNTc4IDUyLjI4MDI4OTMsNDYuMTI3MDM1IEM1My42MTY0Nzk5LDQ1LjQzODEwMjkgNTUuMDc5NzM3Nyw0NS4wODQyMTk4IDU2LjU2OTc5ODcsNDUuMDg0MjE5OCBDNTYuOTUxOTkyOCw0NS4wODQyMTk4IDU3LjMzNzE2NTIsNDUuMTA4MDEwMiA1Ny43MjEzNDQ4LDQ1LjE1NDU5OTkgQzYwLjgzNDQ5MDIsNDUuNTM0MjU2IDYzLjU0OTU1OCw0Ny40MzY1MDE2IDY0Ljk4MTA0ODksNTAuMjQyNzg0NyBDNjUuODM5NzQ1LDUxLjkyNTk1OTggNjYuMTcyMzAzNiw1My44MTEzNTM4IDY1Ljk0Mzk3OTgsNTUuNjkzNzc0MSBMNjUuOTQzOTc5OCw1NS42OTM3NzQxIFogTTY2Ljc1MDA2Miw0OS4zNDM3MDM1IEM2NS4wMTc3NzkzLDQ1Ljk0NzYxNTIgNjEuNzMxOTAyLDQzLjY0NTg4ODEgNTcuOTYxNTgxMSw0My4xODY5MzA1IEM1NS42ODEzMjEzLDQyLjkwODM4MzggNTMuNDAzMDQ2OCw0My4zMTY3ODY4IDUxLjM2ODk3OTYsNDQuMzY1NTQ5NiBDNDcuOTk1NzQzNiw0Ni4xMDYyMTgzIDQ1LjcwODUzNDcsNDkuMzk4MjIzMyA0NS4yNTA4OTQ0LDUzLjE3MDk5MzkgQzQ0Ljc2ODQzNjMsNTcuMTYwODUyNSA0Ni4zNTc3Njg1LDYxLjAzNTcyMzggNDkuNTA0NjY2MSw2My41MzQ3MTM1IEM1MS4xNDU2MTkzLDY0LjgzNzI0MTIgNTMuMTE3MTQ1Nyw2NS42NjA5ODU5IDU1LjIwNDgxOTQsNjUuOTE1NzQyMSBDNTUuNjY3NDIzMyw2NS45NzIyNDQ1IDU2LjEzMDAyNzIsNjYgNTYuNTkxNjM4Myw2NiBDNTguMjcxMzA3Myw2NiA1OS45MzAxMjk0LDY1LjYyOTI2NTMgNjEuNDU1OTI4LDY0LjkwNTYzODggQzYyLjkwMjMwOTYsNjQuMjE5NjgwNSA2NC4yMTc2NTMzLDYzLjIxMjU1MSA2NS4yNTcwMjI5LDYxLjk5NTI3MjQgQzY2LjcyMzI1ODgsNjAuMjgwMzc2NyA2Ny42NDI1MTAzLDU4LjE4Mzg0MjMgNjcuOTE1NTA2MSw1NS45MzE2Nzg3IEM2OC4xOTE0ODAxLDUzLjY1NjcxNTggNjcuNzg4NDM5LDUxLjM3ODc3OTIgNjYuNzUwMDYyLDQ5LjM0MzcwMzUgTDY2Ljc1MDA2Miw0OS4zNDM3MDM1IFogTTI2Ljg5MDY4MjcsNDEuNzU1NTM3OCBMMzAuODYxNTMxNCw0MS43NTU1Mzc4IEwzMC44NjE1MzE0LDM5Ljc3Mjk5OTQgTDI2Ljg5MDY4MjcsMzkuNzcyOTk5NCBMMjYuODkwNjgyNyw0MS43NTU1Mzc4IFogTTE2Ljk2MzU2MDksNDEuNzU1NTM3OCBMMjQuOTA1MjU4Myw0MS43NTU1Mzc4IEwyNC45MDUyNTgzLDM5Ljc3Mjk5OTQgTDE2Ljk2MzU2MDksMzkuNzcyOTk5NCBMMTYuOTYzNTYwOSw0MS43NTU1Mzc4IFogTTE2LjEwNTg1NzYsMTUuOTgyNTM4NCBMNjAuNTA3ODg3OSwxNS45ODI1Mzg0IEM2MS42NzczMDI4LDE1Ljk4MjUzODQgNjIuNjI4MzIxMSwxNy4xMzkzNDk2IDYyLjYyODMyMTEsMTguNTYwODI5NiBMNjIuNjI4MzIxMSwyNS44OTUyMzA1IEw1OS42NTAxODQ1LDI1Ljg5NTIzMDUgTDU5LjY1MDE4NDUsMjAuOTM4ODg0NCBDNTkuNjUwMTg0NSwyMC4zOTE3MDM4IDU5LjIwNjQ0MjIsMTkuOTQ3NjE1MiA1OC42NTc0NzI0LDE5Ljk0NzYxNTIgTDM1LjgyNTA5MjMsMTkuOTQ3NjE1MiBDMzUuMjc2MTIyNCwxOS45NDc2MTUyIDM0LjgzMjM4MDEsMjAuMzkxNzAzOCAzNC44MzIzODAxLDIwLjkzODg4NDQgTDM0LjgzMjM4MDEsMjUuODk1MjMwNSBMMTMuOTg1NDI0NCwyNS44OTUyMzA1IEwxMy45ODU0MjQ0LDE4LjU2MDgyOTYgQzEzLjk4NTQyNDQsMTcuMTYzMTQgMTQuOTU3Mjg5NiwxNS45ODI1Mzg0IDE2LjEwNTg1NzYsMTUuOTgyNTM4NCBMMTYuMTA1ODU3NiwxNS45ODI1Mzg0IFogTTQ3LjI1NjE3MywyNS42MDc3NjI0IEM0OS41NjEyNTA3LDI1LjYwNzc2MjQgNTEuNDM2NDg0LDI3LjQ2MTQzNTggNTEuNDM2NDg0LDI5LjczOTM3MjUgQzUxLjQzNjQ4NCwzMS4yNDExNDUzIDUwLjYwNzU2OTMsMzIuNjIyOTc0NiA0OS4yNzMzNjQyLDMzLjM0NjYwMTEgQzQ4LjAwNjY2MzQsMzQuMDMzNTUwNyA0Ni40Nzk4NzIxLDM0LjAyNDYyOTIgNDUuMjMwMDQ3NCwzMy4zNDc1OTI0IEM0My45MDA4MDU4LDMyLjYyMTk4MzMgNDMuMDc1ODYyLDMxLjI0MDE1NCA0My4wNzU4NjIsMjkuNzM5MzcyNSBDNDMuMDc1ODYyLDI3LjQ2MTQzNTggNDQuOTUwMTAyNiwyNS42MDc3NjI0IDQ3LjI1NjE3MywyNS42MDc3NjI0IEw0Ny4yNTYxNzMsMjUuNjA3NzYyNCBaIE0xMy45ODU0MjQ0LDQ3LjEwODM5MTUgTDEzLjk4NTQyNDQsMjcuODc3NzY4OSBMMzQuODMyMzgwMSwyNy44Nzc3Njg5IEwzNC44MzIzODAxLDQ0LjcyOTM0NTQgQzM0LjgzMjM4MDEsNDUuMjc3NTE3MyAzNS4yNzYxMjI0LDQ1LjcyMDYxNDYgMzUuODI1MDkyMyw0NS43MjA2MTQ2IEw0Ni4yMDI5MDU0LDQ1LjcyMDYxNDYgTDQ2LjIwMjkwNTQsNDMuNzM4MDc2MiBMMzcuOTExNzczMyw0My43MzgwNzYyIEMzNy45OTgxMzkyLDM5Ljc3MTAxNjggNDAuNjM1Nzc1NSwzNi4zNDQxOTkyIDQ0LjQzMzg5MjMsMzUuMjQ5ODM4IEM0Ni4xODkwMDc0LDM2LjA2OTYxNzYgNDguMjg0NjIyOCwzNi4wNzc1NDc4IDUwLjA2NjU0MTIsMzUuMjQ4ODQ2NyBDNTIuMjI4NjY4MywzNS44NzMzNDYzIDU0LjEyMDc3NzcsMzcuMzE3NjI1NSA1NS4yOTMxNzA4LDM5LjI1MzU3NDMgTDU2Ljk5MTcwMTMsMzguMjI2NjE5NCBDNTUuNzg4NTM0MiwzNi4yNDMwODk3IDUzLjk2MjkzNjUsMzQuNjk0NzI3MiA1MS44NDU0ODE0LDMzLjc5NDY1NDggQzUyLjgzODE5MzYsMzIuNjk0MzQ2IDUzLjQyMTkwODMsMzEuMjYyOTUzMiA1My40MjE5MDgzLDI5LjczOTM3MjUgQzUzLjQyMTkwODMsMjYuMzY4MDY1OSA1MC42NTUyMTk1LDIzLjYyNTIyNCA0Ny4yNTYxNzMsMjMuNjI1MjI0IEM0My44NTYxMzM4LDIzLjYyNTIyNCA0MS4wOTA0Mzc3LDI2LjM2ODA2NTkgNDEuMDkwNDM3NywyOS43MzkzNzI1IEM0MS4wOTA0Mzc3LDMxLjI1NzAwNTYgNDEuNjY4MTk2MiwzMi42ODM0NDIgNDIuNjUzOTU5MywzMy43ODM3NTA4IEM0MC4wMDA0Mzk3LDM0Ljg5OTkxOTkgMzcuOTI3NjU2NywzNi45OTI0ODkyIDM2LjgxNzgwNDUsMzkuNTcyNzYzIEwzNi44MTc4MDQ1LDIxLjkzMDE1MzYgTDU3LjY2NDc2MDIsMjEuOTMwMTUzNiBMNTcuNjY0NzYwMiwzNy43OTA0NjA5IEw1OS42NTAxODQ1LDM3Ljc5MDQ2MDkgTDU5LjY1MDE4NDUsMjcuODc3NzY4OSBMNjIuNjI4MzIxMSwyNy44Nzc3Njg5IEw2Mi42MjkzMTM4LDQyLjc0NjgwNyBMNjQuNjE0NzM4Miw0Mi43NDY4MDcgTDY0LjYxMzc0NTQsMTguNTYwODI5NiBDNjQuNjEzNzQ1NCwxNi4wNDU5Nzk2IDYyLjc3MjI2NDMsMTQgNjAuNTA3ODg3OSwxNCBMMTYuMTA1ODU3NiwxNCBDMTMuODQxNDgxMSwxNCAxMiwxNi4wNDU5Nzk2IDEyLDE4LjU2MDgyOTYgTDEyLDQ3LjEwODM5MTUgQzEyLDQ5LjYyMzI0MTUgMTMuODQxNDgxMSw1MS42NjgyMjk4IDE2LjEwNTg1NzYsNTEuNjY4MjI5OCBMNDIuNzc0MDc3NSw1MS42NjgyMjk4IEw0Mi43NzQwNzc1LDQ5LjY4NTY5MTQgTDE2LjEwNTg1NzYsNDkuNjg1NjkxNCBDMTQuOTU3Mjg5Niw0OS42ODU2OTE0IDEzLjk4NTQyNDQsNDguNTA2MDgxMSAxMy45ODU0MjQ0LDQ3LjEwODM5MTUgTDEzLjk4NTQyNDQsNDcuMTA4MzkxNSBaIiBpZD0iQW1hem9uLUNvZ25pdG9fSWNvbl82NF9TcXVpZCIgZmlsbD0iI0ZGRkZGRiI+PC9wYXRoPgogICAgPC9nPgo8L3N2Zz4=