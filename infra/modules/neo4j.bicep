param location string
param containerAppEnvironmentId string
param containerAppName string
param neo4jBoltPort int
param envStorageName string
param keyVaultUri string

resource neo4jApp 'Microsoft.App/containerApps@2026-01-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        transport: 'tcp'
        targetPort: neo4jBoltPort
        exposedPort: neo4jBoltPort
      }
      secrets: [
        {
          name: 'neo4j-auth'
          keyVaultUrl: '${keyVaultUri}secrets/neo4j-auth'
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'neo4j'
          image: 'neo4j:5'
          env: [
            { name: 'NEO4J_AUTH', secretRef: 'neo4j-auth' }
            { name: 'NEO4J_PLUGINS', value: '["apoc"]' }
            {
              name: 'NEO4J_dbms_security_procedures_unrestricted'
              value: 'apoc.text.clean,apoc.refactor.mergeNodes'
            }
            {
              name: 'NEO4J_dbms_security_procedures_allowlist'
              value: 'apoc.text.clean,apoc.refactor.mergeNodes'
            }
          ]
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          volumeMounts: [
            {
              volumeName: 'neo4j-data'
              mountPath: '/data'
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'neo4j-data'
          storageType: 'AzureFile'
          storageName: envStorageName
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          {
            name: 'bolt-tcp-scale'
            tcp: {
              metadata: {
                concurrentConnections: '1'
              }
            }
          }
        ]
      }
    }
  }
}

output fqdn string = neo4jApp.properties.configuration.ingress.fqdn
output principalId string = neo4jApp.identity.principalId
output name string = neo4jApp.name
