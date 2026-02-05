# Create the User
resource "aws_iam_user" "streamlit" {
  name = "${var.project_name}-streamlit-bot-${var.environment}"
}

# Generate Credentials (Access Key + Secret)
resource "aws_iam_access_key" "streamlit" {
  user = aws_iam_user.streamlit.name
}

# Attach Policy: ALLOW Uploads to the NEW Bucket
resource "aws_iam_user_policy" "streamlit_s3" {
  name = "StreamlitS3Access"
  user = aws_iam_user.streamlit.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectTagging",
          "s3:GetObjectTagging",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          aws_s3_bucket.docs.arn,          # The Bucket
          "${aws_s3_bucket.docs.arn}/*"    # The Objects
        ]
      }
    ]
  })
}