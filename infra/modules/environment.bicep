param location string
param logAnalyticsName string
param containerAppEnvName string

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2025-07-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// Platform-managed networking (no vnetConfiguration/custom VNet) —
// deliberately dropped the custom VNet this environment used to carry
// solely so Neo4j could take external TCP (Bolt) ingress. Bringing your own
// VNet bills a Standard Load Balancer + a static public IP 24/7 regardless
// of traffic (see custom-virtual-networks#managed-resources); Neo4j is now
// internal-only (see neo4j.bicep), which needs none of that — container
// apps in the same environment reach each other over Bolt via the
// platform's own internal DNS without any VNet at all.
resource containerAppEnv 'Microsoft.App/managedEnvironments@2026-03-02-preview' = {
  name: containerAppEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

output environmentId string = containerAppEnv.id
output environmentName string = containerAppEnv.name
output logAnalyticsName string = logAnalytics.name
