param location string
param storageAccountName string
param fileShareName string
param fileShareQuotaGb int
param containerAppEnvironmentName string
param envStorageName string

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
