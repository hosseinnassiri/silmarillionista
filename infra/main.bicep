// Resource-group-scope template for the Silmarillion Agent.
// Deployed by .github/workflows/infra.yml via `az deployment group create`.
// All parameter values are passed explicitly by that workflow (non-secret
// defaults live in the workflow YAML, secrets come from GitHub Actions
// repo secrets) rather than a committed .bicepparam file, to avoid mixing
// bicepparam + CLI parameter overrides in the same deployment call.

targetScope = 'resourceGroup'

@description('Azure region for all resources. Confirm Azure OpenAI model/region availability before first apply — text-embedding-3-large availability in canadacentral specifically (vs. canadaeast) was unconfirmed as of planning.')
param location string = 'canadacentral'

// Naming follows the Azure Cloud Adoption Framework recommendations:
// {resource-type-abbreviation}-{workload}-{environment}-{region}-{instance},
// using the official abbreviations from
// https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations
// (rg, log, cae, ca, oai) and the community-standard 'cac' region code for
// Canada Central (CAF publishes no official region abbreviations). Container
// Registry is the one exception — ACR names must be alphanumeric only, no
// hyphens, so its 'cr' prefix is concatenated instead (see acrName below).
@description('Workload name used across all resource names.')
param workloadName string = 'silmarillion'

@description('Environment name used across all resource names.')
param environmentName string = 'prod'

@description('Region abbreviation used across all resource names (community convention — CAF has no official region abbreviation list).')
param regionAbbreviation string = 'cac'

@description('Instance suffix used across all resource names.')
param instanceNumber string = '001'

@description('Container image the Container App starts with. deploy.yml owns this field after the first apply — infra.yml must never override it, so the running image is never rolled back to this placeholder.')
param containerAppImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Azure Container Registry name (globally unique, alphanumeric only, CAF cr prefix concatenated per ACR naming rules). Verify availability with `az acr check-name` before first apply.')
param acrName string = 'cr${workloadName}${environmentName}${regionAbbreviation}${instanceNumber}'

@description('Object ID of the GitHub Actions deploy service principal (silmarillion-agent-deploy), granted AcrPush so deploy.yml can push new images.')
param deployServicePrincipalObjectId string

@description('Azure OpenAI chat deployment name.')
param chatDeploymentName string = 'gpt-5.5'

@description('Azure OpenAI chat model name as it appears in the Azure model catalog. Plain gpt-5 (2025-08-07) has NO pay-as-you-go GlobalStandard SKU left anywhere — only GlobalProvisionedManaged (reserved capacity, min 15 units, billed hourly regardless of use). gpt-5.5 is the current GA flagship confirmed to have GlobalStandard in canadacentral as of the last apply.')
param chatModelName string = 'gpt-5.5'

@description('Azure OpenAI chat model version. CONFIRM against `az cognitiveservices model list --location <region>` before first apply if this changes — catalog availability, not just region, has to be checked per model+version, not assumed from the model name alone.')
param chatModelVersion string = '2026-04-24'

@description('Chat deployment capacity in units of 1K tokens/minute. Kept low as the primary abuse/cost guardrail.')
param chatModelCapacity int = 10

@description('Azure OpenAI embedding deployment name.')
param embeddingDeploymentName string = 'text-embedding-3-large'

@description('Embedding model version. Same caveat as chatModelVersion.')
param embeddingModelVersion string = '1'

@description('Embedding deployment capacity in units of 1K tokens/minute.')
param embeddingModelCapacity int = 10

@description('Azure OpenAI API version the app code targets.')
param azureOpenAiApiVersion string = '2024-10-21'

@description('Neo4j Bolt port, used for both the container and its TCP ingress.')
param neo4jBoltPort int = 7687

@description('Azure Files share quota for Neo4j data, in GB.')
param neo4jFileShareQuotaGb int = 20

@description('Minimum Container App replicas. 0 = scale to zero when idle.')
param minReplicas int = 0

@description('Maximum Container App replicas — hard cap on worst-case concurrent cost.')
param maxReplicas int = 2

@description('Port the app listens on inside the container.')
param targetPort int = 8000

@description('Monthly budget amount in USD.')
param budgetAmount int = 50

@description('Email notified at 50/80/100% of the monthly budget.')
param budgetContactEmail string = 'hossein.nassiri@gmail.com'

@description('First day of the current month, used as the budget start date. Do not override — utcNow() is only valid as a parameter default.')
param budgetStartDate string = utcNow('yyyy-MM-01')

var nameSuffix = '${workloadName}-${environmentName}-${regionAbbreviation}-${instanceNumber}'
var logAnalyticsName = 'log-${nameSuffix}'
var containerAppEnvName = 'cae-${nameSuffix}'
var containerAppName = 'ca-${workloadName}-app-${environmentName}-${regionAbbreviation}-${instanceNumber}'
var neo4jContainerAppName = 'ca-${workloadName}-neo4j-${environmentName}-${regionAbbreviation}-${instanceNumber}'
var openAiAccountName = 'oai-${nameSuffix}'
var budgetName = 'budget-${workloadName}-${environmentName}-${instanceNumber}'
// Storage account names are capped at 24 chars and alphanumeric-only —
// same special rule as ACR. At the current name components this resolves
// to exactly 24 ('stsilmarillionprodcac001'); lengthening workloadName,
// environmentName or regionAbbreviation will overflow the limit.
var storageAccountName = 'st${workloadName}${environmentName}${regionAbbreviation}${instanceNumber}'
var neo4jFileShareName = 'neo4j-data'
var neo4jEnvStorageName = 'neo4j-data'
// Deterministic per resource group rather than a stored secret — Neo4j is
// only reachable over Bolt with this password (see neo4jApp ingress below),
// so there's no external account/GitHub secret needed for it anymore.
var neo4jPassword = guid(resourceGroup().id, 'neo4j-admin-password')
var neo4jUsername = 'neo4j'

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

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
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

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource neo4jFileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileService
  name: neo4jFileShareName
  properties: {
    shareQuota: neo4jFileShareQuotaGb
  }
}

resource neo4jEnvStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerAppEnv
  name: neo4jEnvStorageName
  properties: {
    azureFile: {
      accountName: storageAccount.name
      accountKey: storageAccount.listKeys().keys[0].value
      shareName: neo4jFileShareName
      accessMode: 'ReadWrite'
    }
  }
}

// Self-hosted Neo4j Community Edition (Aura Free's replacement) — same
// Cypher/APOC surface the app code already targets, no code changes needed.
// External TCP ingress (not internal-only) so the existing local scripts
// (src/graph/extract.py, dedupe.py, timeline.py, query.py) can still reach
// it directly, same as they did against the local Docker instance. Traffic
// isn't TLS-wrapped at the Container Apps layer for raw TCP ingress — an
// accepted tradeoff for a personal project, protected by the auto-generated
// password above rather than transport encryption.
resource neo4jApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: neo4jContainerAppName
  location: location
  properties: {
    managedEnvironmentId: containerAppEnv.id
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
          value: '${neo4jUsername}/${neo4jPassword}'
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
          storageName: neo4jEnvStorageName
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
  dependsOn: [
    neo4jEnvStorage
  ]
}

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
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

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
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

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
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

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: targetPort
        transport: 'auto'
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'azure-openai-api-key'
          value: openAiAccount.listKeys().key1
        }
        {
          name: 'neo4j-password'
          value: neo4jPassword
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
            { name: 'AZURE_OPENAI_ENDPOINT', value: openAiAccount.properties.endpoint }
            { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
            { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT', value: chatDeploymentName }
            { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: embeddingDeploymentName }
            { name: 'NEO4J_URI', value: 'bolt://${neo4jApp.properties.configuration.ingress.fqdn}:${neo4jBoltPort}' }
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

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var acrPushRoleId = '8311e382-0749-4cb8-b61a-304f252e45ec'

// Lets the Container App's own managed identity pull from ACR at runtime —
// no stored credential, unlike the GHCR PAT approach this replaced.
resource acrPullForContainerApp 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, containerApp.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Lets deploy.yml's GitHub Actions service principal push new images.
// Contributor (already granted at the resource-group scope) covers managing
// the ACR resource itself, but push/pull are ACR data-plane actions and need
// this explicit data-plane role.
resource acrPushForDeployPrincipal 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, deployServicePrincipalObjectId, acrPushRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPushRoleId)
    principalId: deployServicePrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}

resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: budgetName
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
    }
    notifications: {
      threshold50: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 50
        contactEmails: [budgetContactEmail]
      }
      threshold80: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        contactEmails: [budgetContactEmail]
      }
      threshold100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        contactEmails: [budgetContactEmail]
      }
    }
  }
}

output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppName string = containerApp.name
output openAiEndpoint string = openAiAccount.properties.endpoint
output logAnalyticsName string = logAnalytics.name
output acrLoginServer string = acr.properties.loginServer

// So local scripts (src/graph/extract.py, dedupe.py, timeline.py, query.py)
// and .env can point at this instance the same way they pointed at Aura —
// retrieve with `az deployment group show ... --query properties.outputs`.
output neo4jUri string = 'bolt://${neo4jApp.properties.configuration.ingress.fqdn}:${neo4jBoltPort}'
output neo4jUsername string = neo4jUsername
@secure()
output neo4jPassword string = neo4jPassword
