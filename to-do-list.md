Vector DB: Upstash
* [x] Create an account with free plan
* [x] Create Gemini API key for embeddings
* [x] Connect to Upstash, see [here](/src/db_init/db_init.py)

Authentication
* [x] Create Amazon Cognito user pool id and client id
* [x] Connect to it
* [x] Sign up
* [x] Log in
* [x] Forgot password







## 1. System Architecture

We strictly separate **Storage**, **Compute**, and **Interface**. The frontend (Streamlit) never touches the database directly. It only speaks to authenticated API endpoints.

```mermaid
graph TD
    User((User)) -->|HTTPS| UI[Streamlit App]
    
    subgraph "Auth Tier"
        UI -->|Login| Cognito[Amazon Cognito]
        Cognito -->|JWT Token| UI
    end

    subgraph "Data Plane (Secure Uploads)"
        UI -->|1. Request Upload URL| API_Gen[Generator Lambda]
        API_Gen -->|2. Generate Presigned URL| UI
        UI -->|3. PUT PDF| S3[S3 Bucket \n(Private)]
    end

    subgraph "Ingestion Pipeline (Async)"
        S3 -->|ObjectCreated Event| Ingest[Ingest Lambda]
        Ingest -->|Get PDF| S3
        Ingest -->|Generate Embedding| Gemini[Google Gemini API]
        Ingest -->|Store Vector| Upstash[Upstash Vector DB]
    end

    subgraph "Query Pipeline"
        UI -->|4. Chat Query + JWT| API_Gen
        API_Gen -->|Verify Token| Cognito
        API_Gen -->|Search| Upstash
        API_Gen -->|Generate Answer| Gemini
    end

```

---

## 2. Project Structure

Organize your folders like this to keep infrastructure and code separate.

```text
/my-rag-project
├── /infrastructure          # CloudFormation or Terraform templates
├── /src
│   ├── /auth                
│   ├── /ingest_service      # Lambda 1: Process PDFs
│   │   └── lambda_function.py
│   └── /chat_service        # Lambda 2: Chat & Uploads
│       └── lambda_function.py
├── /frontend
│   ├── .streamlit/secrets.toml  # LOCAL ONLY. Never commit this.
│   ├── auth.py              # Cognito helper functions
│   ├── app.py               # Main UI logic
│   └── requirements.txt     # Frontend libs
└── README.md
```

# CHECK LIST
---

### 1. Identity Tier (AWS Cognito)

*Goal: Secure user management without writing auth code.*

**Go to AWS Console > Amazon Cognito > User Pools > Create user pool**

* **Sign-in experience:**
* [ ] **Provider:** Email
* [ ] **Username:** Do NOT use username (Email only)
* [ ] **Password Policy:** Default (or set to "Low" for dev)
* [ ] **MFA:** No MFA (Simpler for now)


* **Sign-up experience:**
* [ ] **Self-service registration:** Enabled (Allow users to sign up themselves)
* [ ] **Attribute verification:** Send email message, verify email
* [ ] **Required attributes:** `email` only


* **Email delivery:**
* [ ] **Email provider:** Send email with Cognito (Free tier limit is fine)


* **App integration:**
* [ ] **User pool name:** `rag-users`
* [ ] **Domain:** Skip (Not needed for Streamlit native auth)
* [ ] **App client type:** Public client
* [ ] **App client name:** `rag-client`
* [ ] **Client secret:** **DO NOT GENERATE** (Crucial for Streamlit)
* [ ] **Authentication flows:** ALLOW_USER_PASSWORD_AUTH (Tick this box!)



---

### 2. The Brain (Upstash & Gemini)

*Goal: Set up the AI and Database limits.*

**Go to Google AI Studio**

* [ ] **Get API Key:** Create new API key.
* *Copy this key to a notepad.*



**Go to Upstash Console**

* [ ] **Create Vector Index:**
* [ ] **Name:** `rag-index`
* [ ] **Region:** US-East-1 (North Virginia)
* [ ] **Dimensions:** `768` (Critical: Must match Gemini's model)
* [ ] **Distance Metric:** `Cosine`
* [ ] **Plan:** Free (Serverless)



---

### 3. Storage Tier (Amazon S3)

*Goal: Create the secure vault for files.*

**Go to AWS Console > S3 > Create Bucket**

* **General configuration:**
* [ ] **Bucket Name:** `[unique-name]-rag-storage`
* [ ] **AWS Region:** us-east-1 (Keep it consistent)


* **Object Ownership:**
* [ ] **ACLs:** ACLs disabled (Recommended)


* **Block Public Access settings:**
* [ ] **Block all public access:** CHECKED (Security First)


* **Bucket Versioning:**
* [ ] **Versioning:** Enable (Backup in case you overwrite a file)


* **Default encryption:**
* [ ] **Encryption type:** Server-side encryption with Amazon S3 managed keys (SSE-S3)



---

### 4. Compute Configuration (AWS Lambda)

*Goal: Define the "containers" for your code. We are NOT uploading code yet, just configuring the settings.*

**Go to AWS Console > Lambda > Functions > Create function**

#### **Function A: The Ingestor (Background Worker)**

* **Basic Info:**
* [ ] **Name:** `rag-ingest-worker`
* [ ] **Runtime:** Python 3.11
* [ ] **Architecture:** x86_64


* **Configuration Tab > General Configuration:**
* [ ] **Timeout:** Increase to `1 min 30 sec` (PDFs take time)
* [ ] **Memory:** Increase to `512 MB` (PDF processing is heavy)


* **Configuration Tab > Environment Variables:**
* [ ] Add `GEMINI_API_KEY` (Value: from step 2)
* [ ] Add `UPSTASH_VECTOR_REST_URL` (Value: from step 2)
* [ ] Add `UPSTASH_VECTOR_REST_TOKEN` (Value: from step 2)



#### **Function B: The API (Chat Backend)**

* **Basic Info:**
* [ ] **Name:** `rag-chat-api`
* [ ] **Runtime:** Python 3.11


* **Configuration Tab > General Configuration:**
* [ ] **Timeout:** `30 sec` (Chat should be fast)
* [ ] **Memory:** `128 MB` (Default is fine)


* **Configuration Tab > Function URL:**
* [ ] **Create Function URL:** Click it.
* [ ] **Auth type:** NONE (We will handle auth logic later)
* [ ] **CORS:** Configure Cross-Origin Resource Sharing (Check this box!)
* [ ] **Allow origin:** `*`
* [ ] **Allow methods:** `*`





---

### 5. IAM Permissions (The Security Guards)

*Goal: Give the Lambdas permission to touch S3 and Logging.*

**Go to AWS Console > IAM > Roles**

* **Ingest Role (Auto-created for Function A):**
* [ ] Click "Add permissions" > "Attach policies"
* [ ] Search & Tick: `AmazonS3ReadOnlyAccess`


* **Chat API Role (Auto-created for Function B):**
* [ ] Click "Add permissions" > "Attach policies"
* [ ] Search & Tick: `AmazonS3FullAccess` (Simplifying for now, allows Uploads)



---

### **Summary of "Tickbox" Phase**

If you complete this checklist, you have successfully:

1. Created a secure user database.
2. Provisioned a serverless vector database.
3. Set up an encrypted file storage.
4. Created the compute containers (Lambdas) waiting for code.
5. Configured the networking (CORS/Region).

**Next Step:**
Are you happy with this configuration? If yes, the next logical step (when you are ready) is to simply **upload the zip files** (which I can provide) into the two Lambda functions you just created. No coding required on your end, just "Upload".