# --- IAM Role ---
resource "aws_iam_role" "main" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# Basic Logging Permission
resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.main.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# S3 Permission (Read/Write + Tagging)
resource "aws_iam_role_policy" "s3_access" {
  name = "s3_access"
  role = aws_iam_role.main.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject", 
        "s3:ListBucket", 
        "s3:PutObject",
        "s3:PutObjectTagging",
        "s3:GetObjectTagging" 
      ]
      Resource = [
        aws_s3_bucket.docs.arn,
        "${aws_s3_bucket.docs.arn}/*"
      ]
    }]
  })
}

# --- 2. INGEST Lambda ---
resource "aws_lambda_function" "ingest" {
  function_name = "${var.project_name}-ingestLambda"
  role          = aws_iam_role.main.arn
  package_type  = "Image"
  image_uri = "${aws_ecr_repository.ingest.repository_url}:${var.image_tag}"
  timeout       = 300
  memory_size   = 1024

  environment {
    variables = {
      S3_BUCKET_NAME = aws_s3_bucket.docs.bucket
      GOOGLE_API_KEY      = var.google_api_key
      PINECONE_API_KEY    = var.pinecone_api_key
      PINECONE_INDEX_NAME = var.pinecone_index_name
      NEO4J_URI           = var.neo4j_uri
      NEO4J_USERNAME      = var.neo4j_username
      NEO4J_PASSWORD      = var.neo4j_password
    }
  }
}

# Permission for S3 to invoke Ingest Lambda
resource "aws_lambda_permission" "allow_s3_ingest" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.docs.arn
}

# S3 Bucket Notification (The Trigger)
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.docs.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingest.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix = ".pdf"
  }

  # Critical: S3 needs permission BEFORE creating the notification
  depends_on = [aws_lambda_permission.allow_s3_ingest]
}

# --- QUERY Lambda & Function URL ---
resource "aws_lambda_function" "query" {
  function_name = "${var.project_name}-queryLambda"
  role          = aws_iam_role.main.arn
  package_type  = "Image"
  image_uri = "${aws_ecr_repository.query.repository_url}:${var.image_tag}"
  timeout       = 60
  memory_size   = 512

  environment {
    variables = {
      GOOGLE_API_KEY      = var.google_api_key
      PINECONE_API_KEY    = var.pinecone_api_key
      PINECONE_INDEX_NAME = var.pinecone_index_name
      NEO4J_URI           = var.neo4j_uri
      NEO4J_USERNAME      = var.neo4j_username
      NEO4J_PASSWORD      = var.neo4j_password
    }
  }
}

# Enable Public Function URL
resource "aws_lambda_function_url" "query_url" {
  function_name      = aws_lambda_function.query.function_name
  authorization_type = "NONE" # Public
  
  cors {
    allow_origins = ["*"] 
    allow_methods = ["POST"]
    allow_headers = ["content-type"]
  }
}

# Allow public access to the URL
resource "aws_lambda_permission" "allow_public_url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.query.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}