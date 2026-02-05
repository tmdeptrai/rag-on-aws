variable "aws_region" {
  description = "AWS Region to deploy"
  default = "eu-west-1"
}

variable "project_name" {
  description = "Project name prefixes"
  default = "rag-on-aws"
}

variable "environment" {
  description = "Deploy environment"
  default = "prod"
}

variable "image_tag" {
  description = "Docker image tag to deploy (e.g. git sha)"
  default     = "latest" # Fallback for local testing
}

variable "google_api_key" {
  description = "Gemini API Key"
  sensitive   = true 
}

variable "pinecone_api_key" {
  description = "Pinecone Vector DB Key"
  sensitive   = true
}

variable "pinecone_index_name" {
  description = "Pinecone Index Name"
  default     = "rag-on-aws-pinecone"
}

variable "neo4j_uri" {
  description = "Neo4j Connection URI"
  sensitive   = true

}

variable "neo4j_username" {
  description = "Neo4j Username"
}

variable "neo4j_password" {
  description = "Neo4j Password"
  sensitive   = true
}