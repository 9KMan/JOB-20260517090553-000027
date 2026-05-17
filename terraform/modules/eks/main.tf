locals {
  module_name  = "eks-cluster"
  cluster_role_name = "${var.cluster_name}-${var.environment}"
  default_tags = merge(var.tags, { module = local.module_name })
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "eks_cluster_policy" {
  statement {
    sid = "EKSCluster"
    actions = [
      "eks:DescribeCluster",
      "eks:ListClusters"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "eks_cluster_role" {
  name = local.cluster_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "eks.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = local.default_tags
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster_role.name
}

resource "aws_iam_role_policy_attachment" "eks_service_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSServicePolicy"
  role       = aws_iam_role.eks_cluster_role.name
}

resource "aws_eks_cluster" "main" {
  name     = "${var.cluster_name}-${var.environment}"
  role_arn = aws_iam_role.eks_cluster_role.arn
  version  = var.kubernetes_version

  vpc_config {
    subnet_ids              = concat(var.private_subnet_ids, var.public_subnet_ids)
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = ["0.0.0.0/0"]
  }

  kubernetes_network_config {
    ip_family = "ipv4"
    service_ipv4_cidr = "172.20.0.0/16"
  }

  encryption_config {
    provider {
      key_arn = aws_kms_key.eks_key.arn
    }
    resources = ["secrets"]
  }

  tags = local.default_tags

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy,
    aws_iam_role_policy_attachment.eks_service_policy
  ]
}

resource "aws_kms_key" "eks_key" {
  description = "KMS key for EKS secrets encryption"
  policy      = jsonencode({
    Version = "2012-10-17"
    Id      = "key-policy-eks"
    Statement = [{
      Sid       = "Enable IAM User Permissions"
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
      Action    = "kms:*"
      Resource  = "*"
    }, {
      Sid    = "Allow EKS to use the key"
      Effect = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = ["kms:Encrypt", "kms:Decrypt", "kms:DescribeKey"]
      Resource  = "*"
    }]
  })

  tags = local.default_tags
}

resource "aws_kms_alias" "eks_key_alias" {
  name          = "alias/eks-${var.cluster_name}-${var.environment}"
  target_key_id = aws_kms_key.eks_key.key_id
}

resource "aws_iam_role" "eks_nodes_role" {
  name = "${var.cluster_name}-nodes-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = local.default_tags
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_nodes_role.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_nodes_role.name
}

resource "aws_iam_role_policy_attachment" "eks_container_registry_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_nodes_role.name
}

resource "aws_iam_openid_connect_provider" "eks_oidc" {
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = ["9e99a48a0b6a69fa0f81c7d4b80e60a6b9db4f37"]
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_eks_node_group" "general" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "general-workers"
  node_role_arn   = aws_iam_role.eks_nodes_role.arn
  subnet_ids      = var.private_subnet_ids
  instance_types   = var.worker_instance_types

  disk_size = var.worker_disk_size

  scaling_config {
    min_size        = var.min_worker_count
    max_size        = var.max_worker_count
    desired_size    = var.desired_worker_count
  }

  labels = {
    workload = "general"
  }

  taint {
    key    = "workload"
    value  = "general"
    effect = "NO_SCHEDULE"
  }

  tags = local.default_tags

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.eks_container_registry_policy
  ]
}

resource "aws_eks_node_group" "gpu" {
  count = var.enable_gpu_workers ? 1 : 0

  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "gpu-workers"
  node_role_arn   = aws_iam_role.eks_nodes_role.arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = ["p3.2xlarge", "g4dn.xlarge"]

  disk_size = var.worker_disk_size

  scaling_config {
    min_size        = 0
    max_size        = 5
    desired_size    = 0
  }

  labels = {
    workload = "gpu"
    type     = "nvidia"
  }

  taint {
    key    = "gpu"
    value  = "enabled"
    effect = "NO_SCHEDULE"
  }

  tags = local.default_tags

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.eks_container_registry_policy
  ]
}

resource "aws_cloudwatch_log_group" "eks_logs" {
  name              = "/aws/eks/${var.cluster_name}-${var.environment}/cluster"
  retention_in_days = 30

  tags = local.default_tags
}

output "cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_certificate_authority_data" {
  description = "EKS cluster CA data"
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "cluster_oidc_issuer_url" {
  description = "OIDC issuer URL"
  value       = aws_eks_cluster.main.identity[0].oidc[0].issuer
}