resource "aws_s3_bucket" "docs" {
  bucket        = "${var.project_name}-docs-${var.environment}"
  force_destroy = true
}

resource "aws_ecr_repository" "ingest" {
  name         = "${var.project_name}-ingest"
  force_delete = true
}

resource "aws_ecr_repository" "query" {
  name         = "${var.project_name}-query"
  force_delete = true
}