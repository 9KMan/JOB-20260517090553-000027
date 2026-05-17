locals {
  module_name = "mlflow-platform"
  environment = var.labels["environment"] != null ? var.labels["environment"] : "dev"
}

data "google_project" "project" {}

resource "google_storage_bucket" "artifacts" {
  count         = var.artifacts_bucket == "" ? 1 : 0
  name          = "${data.google_project.project.project_id}-mlflow-artifacts-${local.module_name}-${local.environment}"
  location      = var.location
  force_destroy = false

  labels = merge(var.labels, {
    module = local.module_name
  })

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 30
    }
  }
}

resource "google_sql_database_instance" "mlflow_db" {
  count = 2

  name             = "${local.module_name}-${count.index == 0 ? "primary" : "replica"}-${local.environment}"
  database_version = count.index == 0 ? "POSTGRES_15" : "POSTGRES_15"
  region           = var.location

  deletion_protection = var.delete_protection

  settings {
    tier              = var.instance_type
    availability_type = count.index == 0 ? "REGIONAL" : "READ_REPLICA"
    disk_size         = var.storage_size_gb
    disk_type         = "PD_SSD"

    backup_configuration {
      enabled                        = var.backup_enabled
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
    }

    ip_configuration {
      ipv4_enabled    = true
      private_network = null
      ssl_mode        = "ENFORCED"
    }

    labels = var.labels
  }
}

resource "google_sql_database" "mlflow_database" {
  name     = "mlflow"
  instance = google_sql_database_instance.mlflow_db[0].name
}

resource "google_sql_user" "mlflow_user" {
  name     = "mlflow_admin"
  instance = google_sql_database_instance.mlflow_db[0].name
  password = var.database_password
}

resource "google_compute_instance" "mlflow_server" {
  name         = "${local.module_name}-server-${local.environment}"
  machine_type = var.instance_type
  zone         = "${var.location}-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 50
    }
  }

  network_interface {
    network = var.vpc_name
    subnetwork = var.subnet_name
  }

  labels = merge(var.labels, {
    component = "mlflow-server"
  })

  service_account = google_service_account.mlflow_sa.email

  metadata = {
    startup-script = <<-EOF
      #!/bin/bash
      apt-get update
      apt-get install -y python3-pip nginx
      pip3 install mlflow==${var.mlflow_version} sqlalchemy psycopg2-binary gunicorn
      mkdir -p /var/log/mlflow
      cat > /etc/systemd/system/mlflow.service << 'SERVICEEOF'
      [Unit]
      Description=MLflow Server
      After=network.target

      [Service]
      Type=simple
      User=root
      WorkingDirectory=/opt/mlflow
      ExecStart=/usr/bin/python3 -m gunicorn -b 0.0.0.0:8000 -w 4 mlflow:app
      Restart=always
      Environment="MLFLOW_TRACKING_URI=postgresql://mlflow_admin:${var.database_password}@${google_sql_database_instance.mlflow_db[0].private_ip_address}/mlflow"
      Environment="MLFLOW_ARTIFACT_ROOT=gs://${var.artifacts_bucket != "" ? var.artifacts_bucket : google_storage_bucket.artifacts[0].name}/"
      Environment="GOOGLE_APPLICATION_CREDENTIALS=/etc/gcp-service-account.json"

      [Install]
      WantedBy=multi-user.target
      SERVICEEOF
      systemctl daemon-reload
      systemctl enable mlflow
      systemctl start mlflow
    EOF
  }

  tags = ["mlflow-server", "allow-http", "allow-https"]
}

resource "google_compute_firewall" "mlflow_fw" {
  name    = "${local.module_name}-allow-http-${local.environment}"
  network = var.vpc_name

  allow {
    protocol = "tcp"
    ports    = ["8000", "80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["mlflow-server"]
}

resource "google_dns_record_set" "mlflow_dns" {
  name         = "mlflow.${var.labels["domain"] != null ? var.labels["domain"] : "example.com"}."
  type         = "A"
  ttl          = 300
  zone         = var.labels["dns_zone"] != null ? var.labels["dns_zone"] : ""
  rrdatas      = [google_compute_instance.mlflow_server.network_interface[0].access_config[0].nat_ip]
}

resource "google_monitoring_alert_policy" "high_cpu" {
  display_name = "${local.module_name} - High CPU Alert"
  conditions {
    display_name = "CPU utilization > 80%"
    condition_threshold {
      filter          = "resource.type = \"gce_instance\" AND metric.type = \"compute.googleapis.com/instance/cpu/utilization\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8
    }
  }

  notification_channels = var.labels["notification_channel"] != null ? [var.labels["notification_channel"]] : []
  severity               = "WARNING"
}

resource "google_monitoring_alert_policy" "high_memory" {
  display_name = "${local.module_name} - High Memory Alert"
  conditions {
    display_name = "Memory utilization > 85%"
    condition_threshold {
      filter          = "resource.type = \"gce_instance\" AND metric.type = \"agent.googleapis.com/memory/byte_count\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.85
    }
  }

  notification_channels = var.labels["notification_channel"] != null ? [var.labels["notification_channel"]] : []
  severity               = "WARNING"
}

output "mlflow_server_ip" {
  description = "MLflow server public IP"
  value       = google_compute_instance.mlflow_server.network_interface[0].access_config[0].nat_ip
}

output "artifacts_bucket" {
  description = "GCS bucket for MLflow artifacts"
  value       = var.artifacts_bucket != "" ? var.artifacts_bucket : google_storage_bucket.artifacts[0].name
}

output "database_connection_string" {
  description = "PostgreSQL connection string"
  value       = "postgresql://mlflow_admin:${var.database_password}@${google_sql_database_instance.mlflow_db[0].private_ip_address}/mlflow"
  sensitive   = true
}