# ==============================================================================
# Terraform Input Variables
# Azure Container Instances (ACI) Observability Stack
# ==============================================================================

variable "resource_group_name" {
  description = "Name of the Azure Resource Group hosting the observability stack"
  type        = string
  default     = "rg-observability-sea"
}

variable "location" {
  description = "Azure region for resource deployment. Defaults to Southeast Asia (allowed for Azure for Students subscriptions)."
  type        = string
  default     = "southeastasia"
}

variable "container_group_name" {
  description = "Name of the Azure Container Group instance"
  type        = string
  default     = "aci-observability-stack"
}

variable "dns_prefix" {
  description = "DNS label prefix for the public FQDN (*.southeastasia.azurecontainer.io)"
  type        = string
  default     = "cloudnotes-obs"
}

variable "tags" {
  description = "Resource tags applied to Azure resources for cost tracking and governance"
  type        = map(string)
  default = {
    Project     = "Containerized-Observability-Stack"
    Environment = "SRE-Demo"
    ManagedBy   = "Terraform"
    CostTier    = "LowCost-Student-Serverless"
  }
}
