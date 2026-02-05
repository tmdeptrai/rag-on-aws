terraform {
    # This stores the tfstate file in a s3 bucket so that 
    #local dev and CI/CD pipeline won't conflict (i.e setting up new infra)
  backend "s3" {
    bucket = "rag-on-aws-tfstate-backend-99"
    key    = "prod/terraform.tfstate"         
    region = "eu-west-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags={
        Project = var.project_name
        Environment = var.environment
        ManagedBy = "Terraform"
    }
  }
}

module "rag_backend" {
  source = "./modules"

  project_name = var.project_name
  environment=var.environment
  image_tag = var.image_tag

  google_api_key      = var.google_api_key
  pinecone_api_key    = var.pinecone_api_key
  pinecone_index_name = var.pinecone_index_name
  neo4j_uri           = var.neo4j_uri
  neo4j_username      = var.neo4j_username
  neo4j_password      = var.neo4j_password
}