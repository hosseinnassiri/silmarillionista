param location string
param openAiAccountName string
param chatDeploymentName string
param chatModelName string
param chatModelVersion string
param chatModelCapacity int
param embeddingDeploymentName string
param embeddingModelVersion string
param embeddingModelCapacity int

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2026-05-15-preview' = {
  name: openAiAccountName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openAiAccountName
    publicNetworkAccess: 'Enabled'
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-05-15-preview' = {
  parent: openAiAccount
  name: chatDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: chatModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: chatModelName
      version: chatModelVersion
    }
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-05-15-preview' = {
  parent: openAiAccount
  name: embeddingDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: embeddingModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingDeploymentName
      version: embeddingModelVersion
    }
  }
  dependsOn: [
    chatDeployment
  ]
}

output endpoint string = openAiAccount.properties.endpoint
output accountName string = openAiAccount.name
