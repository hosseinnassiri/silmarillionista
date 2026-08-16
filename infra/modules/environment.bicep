param location string
param logAnalyticsName string
param containerAppEnvName string
param vnetName string
param infrastructureSubnetName string

@description('VNet address space. Only this environment\'s infrastructure subnet lives here today; wide open for future subnets.')
param vnetAddressPrefix string = '10.0.0.0/16'

@description('Infrastructure subnet for the Container Apps Environment. Consumption-only environments (no workloadProfiles declared, as here) require at least /23 — a workload-profile environment could use a smaller /27, but that\'s a bigger structural change than this fix needs.')
param infrastructureSubnetPrefix string = '10.0.0.0/23'

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

// Required for Neo4j's Bolt port to use external TCP ingress — Azure
// rejects external TCP ingress on Container Apps Environments without a
// custom VNET (ContainerAppTcpRequiresVnet). `internal: false` below keeps
// the environment's own ingress (this app + Neo4j's Bolt port) publicly
// reachable, same as before; only the infrastructure subnet is new.
resource vnet 'Microsoft.Network/virtualNetworks@2026-01-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: [
      {
        name: infrastructureSubnetName
        properties: {
          addressPrefix: infrastructureSubnetPrefix
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
    ]
  }
}

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
    vnetConfiguration: {
      infrastructureSubnetId: vnet.properties.subnets[0].id
      internal: false
    }
  }
}

output environmentId string = containerAppEnv.id
output environmentName string = containerAppEnv.name
output logAnalyticsName string = logAnalytics.name
