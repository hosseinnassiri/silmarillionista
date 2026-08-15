// Shared platform: Log Analytics workspace + Container Apps Environment.
// Both container apps (main app, neo4j) and the future budget/rbac wiring
// depend on this — no dependencies of its own.

param location string
param logAnalyticsName string
param containerAppEnvName string

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
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
