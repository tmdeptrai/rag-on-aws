output "query_endpoint" {
  value       = module.rag_backend.query_lambda_url
  description = "The public URL for your Query Lambda"
}

output "ingest_endpoint" {
  value = module.rag_backend.ingest_repo_url
}

output "query_repo_url" {
  value = module.rag_backend.query_repo_url
}

output "streamlit_access_key" {
  value = module.rag_backend.streamlit_access_key
}

output "streamlit_secret_key" {
  value     = module.rag_backend.streamlit_secret_key
  sensitive = true
}