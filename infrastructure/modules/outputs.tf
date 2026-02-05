output "query_lambda_url" {
  value = aws_lambda_function_url.query_url.function_url
}

output "ingest_repo_url" {
  value = aws_ecr_repository.ingest.repository_url
}

output "query_repo_url" {
  value = aws_ecr_repository.query.repository_url
}

output "streamlit_access_key" {
  value = aws_iam_access_key.streamlit.id
}

output "streamlit_secret_key" {
  value     = aws_iam_access_key.streamlit.secret
  sensitive = true
}