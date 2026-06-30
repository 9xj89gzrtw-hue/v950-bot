# v9.53 Terraform — Infrastructure as Code
# ===========================================
# One command: terraform apply
# Creates: VPC, EKS cluster, RDS, S3, CloudWatch, IAM
#
# Prerequisites:
#   terraform install (https://terraform.io)
#   AWS credentials configured
#
# Usage:
#   cd deploy/terraform
#   terraform init
#   terraform plan
#   terraform apply

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }
  
  # Remote state (S3 + DynamoDB for locking)
  backend "s3" {
    bucket         = "v950-terraform-state"
    key            = "v950-bot/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

# ============================================================================
# VARIABLES
# ============================================================================

variable "aws_region" {
  default = "eu-west-1"
}

variable "cluster_name" {
  default = "v950-bot-cluster"
}

variable "telegram_bot_token" {
  description = "Telegram bot token from @BotFather"
  type        = string
  sensitive   = true
}

variable "telegram_chat_id" {
  description = "Telegram chat ID"
  type        = string
  sensitive   = true
}

# ============================================================================
# PROVIDERS
# ============================================================================

provider "aws" {
  region = var.aws_region
}

# ============================================================================
# VPC + NETWORKING
# ============================================================================

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "v950-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway   = true
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Project = "v950-bot"
  }
}

# ============================================================================
# EKS CLUSTER
# ============================================================================

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.15"

  cluster_name    = var.cluster_name
  cluster_version = "1.28"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Managed node group
  eks_managed_node_groups = {
    bot_nodes = {
      min_size       = 1
      max_size       = 3
      desired_size   = 1
      instance_types = ["t3.medium"]
      
      labels = {
        app = "telegram-bot"
      }
    }
  }

  # IRSA (IAM Roles for Service Accounts)
  enable_irsa = true

  tags = {
    Project = "v950-bot"
  }
}

# ============================================================================
# S3 (state storage + model cache)
# ============================================================================

resource "aws_s3_bucket" "bot_data" {
  bucket = "v950-bot-data-${var.aws_region}"
  
  tags = {
    Project = "v950-bot"
  }
}

resource "aws_s3_bucket_versioning" "bot_data" {
  bucket = aws_s3_bucket.bot_data.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ============================================================================
# SECRETS (Telegram credentials)
# ============================================================================

resource "aws_secretsmanager_secret" "telegram" {
  name        = "v950/telegram-credentials"
  description = "Telegram bot token and chat ID"
}

resource "aws_secretsmanager_secret_version" "telegram" {
  secret_id = aws_secretsmanager_secret.telegram.id
  secret_string = jsonencode({
    bot_token = var.telegram_bot_token
    chat_id   = var.telegram_chat_id
  })
}

# ============================================================================
# CLOUDWATCH MONITORING
# ============================================================================

resource "aws_cloudwatch_log_group" "bot_logs" {
  name              = "/v950/bot"
  retention_in_days = 30
}

resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "v950-bot-high-cpu"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EKS"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "Bot CPU > 80% for 10 min"
  
  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_sns_topic" "alerts" {
  name = "v950-alerts"
}

# ============================================================================
# KUBERNETES RESOURCES (deploy after EKS is ready)
# ============================================================================

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", var.cluster_name]
  }
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", var.cluster_name]
    }
  }
}

# Namespace
resource "kubernetes_namespace" "bot" {
  metadata {
    name = "v950-bot"
    labels = {
      istio-injection = "enabled"
    }
  }
}

# Secret from AWS Secrets Manager
resource "kubernetes_secret" "telegram" {
  metadata {
    name      = "telegram-secrets"
    namespace = kubernetes_namespace.bot.metadata[0].name
  }
  data = {
    bot-token = var.telegram_bot_token
    chat-id   = var.telegram_chat_id
  }
}

# Deploy bot
resource "kubernetes_deployment" "bot" {
  metadata {
    name      = "telegram-bot"
    namespace = kubernetes_namespace.bot.metadata[0].name
  }
  spec {
    replicas = 1
    selector {
      match_labels = {
        app = "telegram-bot"
      }
    }
    template {
      metadata {
        labels = {
          app = "telegram-bot"
        }
      }
      spec {
        container {
          name  = "bot"
          image = "ghcr.io/v950/telegram-bot:latest"
          resources {
            requests = {
              memory = "512Mi"
              cpu    = "250m"
            }
            limits = {
              memory = "2Gi"
              cpu    = "1000m"
            }
          }
          env {
            name = "TELEGRAM_BOT_TOKEN"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.telegram.metadata[0].name
                key  = "bot-token"
              }
            }
          }
          env {
            name = "TELEGRAM_CHAT_ID"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.telegram.metadata[0].name
                key  = "chat-id"
              }
            }
          }
        }
      }
    }
  }
}

# Install Prometheus via Helm
resource "helm_release" "prometheus" {
  name       = "prometheus"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "prometheus"
  namespace  = "monitoring"
  
  create_namespace = true
  
  set {
    name  = "server.persistentVolume.size"
    value = "10Gi"
  }
}

# Install Grafana via Helm
resource "helm_release" "grafana" {
  name       = "grafana"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "grafana"
  namespace  = "monitoring"
  
  set {
    name  = "adminPassword"
    value = "v950-admin"
  }
  
  set {
    name  = "persistence.size"
    value = "5Gi"
  }
}

# ============================================================================
# OUTPUTS
# ============================================================================

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "bot_data_bucket" {
  value = aws_s3_bucket.bot_data.bucket
}

output "secrets_arn" {
  value = aws_secretsmanager_secret.telegram.arn
}
