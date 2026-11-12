# ==============================================================================
# Terraform Infrastructure as Code: Azure Serverless Container Instances (ACI)
# Low-cost serverless multi-container observability deployment (~$0.01 testing)
# ==============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {}
}

# Generate unique suffix for globally unique Azure Container DNS label
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

# Azure Resource Group located in Southeast Asia (Students tier compliant)
resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

# Serverless Azure Container Group running Prometheus, Redis, and Redis-Exporter
# All containers share the localhost network interface inside the group sandbox
resource "azurerm_container_group" "aci" {
  name                = var.container_group_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  ip_address_type     = "Public"
  dns_name_label      = "${var.dns_prefix}-${random_string.suffix.result}"
  os_type             = "Linux"
  restart_policy      = "Always"
  tags                = var.tags

  exposed_port {
    port     = 9090
    protocol = "TCP"
  }

  # Container 1: Prometheus TSDB Monitoring Server
  container {
    name   = "prometheus"
    image  = "prom/prometheus:v2.51.0"
    cpu    = "0.5"
    memory = "0.5"

    ports {
      port     = 9090
      protocol = "TCP"
    }

    volume {
      name       = "prom-config"
      mount_path = "/etc/prometheus"
      secret = {
        "prometheus.yml" = base64encode(<<-EOT
          global:
            scrape_interval: 5s
            evaluation_interval: 5s

          scrape_configs:
            - job_name: "prometheus"
              static_configs:
                - targets: ["localhost:9090"]
                  labels:
                    environment: "azure-aci"
                    service: "prometheus"

            - job_name: "redis-exporter"
              static_configs:
                - targets: ["localhost:9121"]
                  labels:
                    environment: "azure-aci"
                    service: "redis-cache"
        EOT
        )
      }
    }
  }

  # Container 2: Redis In-Memory Data Store & Cache
  container {
    name     = "redis"
    image    = "redis:7.2-alpine"
    cpu      = "0.3"
    memory   = "0.5"
    commands = ["redis-server", "--appendonly", "no"]

    ports {
      port     = 6379
      protocol = "TCP"
    }
  }

  # Container 3: Redis Prometheus Exporter
  container {
    name   = "redis-exporter"
    image  = "oliver006/redis_exporter:v1.58.0-alpine"
    cpu    = "0.2"
    memory = "0.5"

    ports {
      port     = 9121
      protocol = "TCP"
    }

    environment_variables = {
      REDIS_ADDR = "redis://localhost:6379"
    }
  }
}
