# ==============================================================================
# Terraform Outputs
# Azure Container Instances Observability Stack
# ==============================================================================

output "resource_group_name" {
  description = "Name of the provisioned Azure Resource Group"
  value       = azurerm_resource_group.rg.name
}

output "container_group_name" {
  description = "Name of the Azure Container Group instance"
  value       = azurerm_container_group.aci.name
}

output "public_ip_address" {
  description = "Public IPv4 address assigned to the container group"
  value       = azurerm_container_group.aci.ip_address
}

output "fqdn" {
  description = "Public Fully Qualified Domain Name (FQDN) for the container group"
  value       = azurerm_container_group.aci.fqdn
}

output "prometheus_ui_url" {
  description = "Direct URL to access the Prometheus Web UI running live in Azure ACI"
  value       = "http://${azurerm_container_group.aci.fqdn}:9090"
}

output "total_cpu_allocated" {
  description = "Total CPU cores shared across all 3 containers"
  value       = "1.0 vCPU (0.5 Prometheus + 0.3 Redis + 0.2 Redis-Exporter)"
}

output "total_memory_allocated" {
  description = "Total memory shared across all 3 containers"
  value       = "1.5 GB RAM (0.5 GB Prometheus + 0.5 GB Redis + 0.5 GB Redis-Exporter)"
}

output "cost_profile" {
  description = "Cost estimation for student/demo testing"
  value       = "Serverless per-second pricing (~$0.0000125/vCPU-s + ~$0.0000015/GB-s). A 15-minute test costs ~$0.01 USD."
}
