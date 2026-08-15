param location string
param containerAppEnvironmentId string
param containerAppName string
param containerAppImage string
param acrLoginServer string
param targetPort int
param minReplicas int
param maxReplicas int
param azureOpenAiEndpoint string
param azureOpenAiApiVersion string
param chatDeploymentName string
param embeddingDeploymentName string
param neo4jUri string
param neo4jUsername string
param keyVaultUri string

resource containerApp 'Microsoft.App/containerApps@2026-01-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnvironmentId
    configuration: {
      ingress: {
        external: true
        targetPort: targetPort
        transport: 'auto'
      }
      registries: [
        {
          server: acrLoginServer
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'azure-openai-api-key'
          keyVaultUrl: '${keyVaultUri}secrets/azure-openai-api-key'
          identity: 'system'
        }
        {
          name: 'neo4j-password'
          keyVaultUrl: '${keyVaultUri}secrets/neo4j-password'
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'app'
          image: containerAppImage
          env: [
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
            { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
            { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT', value: chatDeploymentName }
            { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: embeddingDeploymentName }
            { name: 'NEO4J_URI', value: neo4jUri }
            { name: 'NEO4J_USERNAME', value: neo4jUsername }
            { name: 'NEO4J_PASSWORD', secretRef: 'neo4j-password' }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output fqdn string = containerApp.properties.configuration.ingress.fqdn
output principalId string = containerApp.identity.principalId
output name string = containerApp.name
