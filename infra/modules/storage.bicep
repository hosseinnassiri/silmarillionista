param location string
param storageAccountName string
param fileShareName string
param fileShareQuotaGb int
param containerAppEnvironmentName string
param envStorageName string
param appPrincipalId string

resource storageAccount 'Microsoft.Storage/storageAccounts@2026-04-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2026-04-01' = {
  parent: storageAccount
  name: 'default'
}

resource neo4jFileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2026-04-01' = {
  parent: fileService
  name: fileShareName
  properties: {
    shareQuota: fileShareQuotaGb
  }
}

// Table Storage for the /ask response cache (src/cache.py) — a separate
// service on this same account, so this adds zero new billable Azure
// resources.
resource tableService 'Microsoft.Storage/storageAccounts/tableServices@2026-04-01' = {
  parent: storageAccount
  name: 'default'
}

resource askCacheTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2026-04-01' = {
  parent: tableService
  name: 'askcache'
}

// Lets the app's managed identity read/write cache rows via azure-identity
// at runtime — no stored account key, same identity+RBAC pattern as ACR
// pull in registry.bicep. Storage Table Data Contributor (role ID verified
// against Microsoft Learn's built-in roles reference).
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

resource tableDataContributorForApp 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, appPrincipalId, storageTableDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2026-01-01' existing = {
  name: containerAppEnvironmentName
}

resource envStorage 'Microsoft.App/managedEnvironments/storages@2026-01-01' = {
  parent: containerAppEnv
  name: envStorageName
  properties: {
    azureFile: {
      accountName: storageAccount.name
      accountKey: storageAccount.listKeys().keys[0].value
      shareName: fileShareName
      accessMode: 'ReadWrite'
    }
  }
}

output envStorageName string = envStorage.name
output storageAccountName string = storageAccount.name
