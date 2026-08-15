targetScope = 'resourceGroup'

@description('Azure region for all resources. Confirm Azure OpenAI model/region availability before first apply — GlobalStandard SKU support varies per model+version+region and can\'t be assumed from the model name alone.')
param location string = 'canadacentral'

// Naming follows the Azure Cloud Adoption Framework recommendations:
// {resource-type-abbreviation}-{workload}-{environment}-{region}-{instance},
@description('Workload name used across all resource names.')
@minLength(1)
param workloadName string = 'silmarillion'

@description('Environment name used across all resource names.')
@minLength(1)
param environmentName string = 'prod'

@description('Region abbreviation used across all resource names (community convention — CAF has no official region abbreviation list).')
@minLength(1)
param regionAbbreviation string = 'cac'

@description('Instance suffix used across all resource names.')
@minLength(1)
param instanceNumber string = '001'

@description('Container image the Container App starts with. deploy.yml owns this field after the first apply — infra.yml must never override it, so the running image is never rolled back to this placeholder.')
param containerAppImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Azure Container Registry name (globally unique, alphanumeric only, CAF cr prefix concatenated per ACR naming rules). Verify availability with `az acr check-name` before first apply.')
param acrName string = 'cr${workloadName}${environmentName}${regionAbbreviation}${instanceNumber}'

@description('Object ID of the GitHub Actions deploy service principal (silmarillion-agent-deploy). Granted AcrPush in modules/registry.bicep and Key Vault Secrets Officer (self-grant) in modules/keyVault.bicep.')
param deployServicePrincipalObjectId string

@description('Azure OpenAI chat deployment name.')
param chatDeploymentName string = 'gpt-5.5'

@description('Azure OpenAI chat model name as it appears in the Azure model catalog. CONFIRM GlobalStandard SKU availability for the exact model+version+region combination against `az cognitiveservices model list --location <region>` before changing this — availability is not consistent across model versions even within the same model family.')
param chatModelName string = 'gpt-5.5'

@description('Azure OpenAI chat model version.')
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

@description('Minimum main-app Container App replicas. 0 = scale to zero when idle.')
param minReplicas int = 0

@description('Maximum main-app Container App replicas — hard cap on worst-case concurrent cost.')
param maxReplicas int = 2

@description('Port the main app listens on inside its container.')
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
// Container App names are capped at 32 chars. 'ca-<workload>-app-<env>-<region>-<instance>'
// lands exactly at 32 for this workload; 'neo4j' (5 chars) is 2 longer than
// 'app' (3), so this one drops the environment segment to fit — same
// tightest-limit-first approach as keyVaultName above.
var neo4jContainerAppName = 'ca-${workloadName}-neo4j-${regionAbbreviation}-${instanceNumber}'
var openAiAccountName = 'oai-${nameSuffix}'
var budgetName = 'budget-${workloadName}-${environmentName}-${instanceNumber}'
var storageAccountName = 'st${workloadName}${environmentName}${regionAbbreviation}${instanceNumber}'
var keyVaultName = 'kv-${workloadName}-${regionAbbreviation}-${instanceNumber}'
var neo4jFileShareName = 'neo4j-data'
var neo4jEnvStorageName = 'neo4j-data'
var neo4jUsername = 'neo4j'
// Computed directly (not read back from registry.outputs/keyVault.outputs)
// so app.bicep/neo4j.bicep don't create a module dependency on
// registry.bicep/keyVault.bicep — those two now depend on app/neo4j
// instead (for the principal IDs their role assignments target), and
// Bicep doesn't allow a two-way module dependency. Both formats are
// deterministic/documented Azure conventions, not a guess.
var acrLoginServer = '${acrName}.azurecr.io'
var keyVaultUri = 'https://${keyVaultName}${az.environment().suffixes.keyvaultDns}/'

module environment 'modules/environment.bicep' = {
  name: 'environment'
  params: {
    location: location
    logAnalyticsName: logAnalyticsName
    containerAppEnvName: containerAppEnvName
  }
}

module openAi 'modules/openAi.bicep' = {
  name: 'openAi'
  params: {
    location: location
    openAiAccountName: openAiAccountName
    chatDeploymentName: chatDeploymentName
    chatModelName: chatModelName
    chatModelVersion: chatModelVersion
    chatModelCapacity: chatModelCapacity
    embeddingDeploymentName: embeddingDeploymentName
    embeddingModelVersion: embeddingModelVersion
    embeddingModelCapacity: embeddingModelCapacity
  }
}

// Depends on app.outputs.principalId for its AcrPull grant — see the
// acrLoginServer var above for why this doesn't create a cycle back.
module registry 'modules/registry.bicep' = {
  name: 'registry'
  params: {
    location: location
    acrName: acrName
    appPrincipalId: app.outputs.principalId
    deployServicePrincipalObjectId: deployServicePrincipalObjectId
  }
}

// Depends on openAi.outputs.accountName (existing-lookup + listKeys() done
// internally) and app/neo4j's principal IDs for its Key Vault Secrets User
// grants — see the keyVaultUri var above for why this doesn't create a
// cycle back.
module keyVault 'modules/keyVault.bicep' = {
  name: 'keyVault'
  params: {
    location: location
    keyVaultName: keyVaultName
    tenantId: subscription().tenantId
    openAiAccountName: openAi.outputs.accountName
    neo4jUsername: neo4jUsername
    appPrincipalId: app.outputs.principalId
    neo4jPrincipalId: neo4j.outputs.principalId
    deployServicePrincipalObjectId: deployServicePrincipalObjectId
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    storageAccountName: storageAccountName
    fileShareName: neo4jFileShareName
    fileShareQuotaGb: neo4jFileShareQuotaGb
    containerAppEnvironmentName: environment.outputs.environmentName
    envStorageName: neo4jEnvStorageName
  }
}

module neo4j 'modules/neo4j.bicep' = {
  name: 'neo4j'
  params: {
    location: location
    containerAppEnvironmentId: environment.outputs.environmentId
    containerAppName: neo4jContainerAppName
    neo4jBoltPort: neo4jBoltPort
    envStorageName: neo4jEnvStorageName
    keyVaultUri: keyVaultUri
  }
  dependsOn: [
    storage
  ]
}

module app 'modules/app.bicep' = {
  name: 'app'
  params: {
    location: location
    containerAppEnvironmentId: environment.outputs.environmentId
    containerAppName: containerAppName
    containerAppImage: containerAppImage
    acrLoginServer: acrLoginServer
    targetPort: targetPort
    minReplicas: minReplicas
    maxReplicas: maxReplicas
    azureOpenAiEndpoint: openAi.outputs.endpoint
    azureOpenAiApiVersion: azureOpenAiApiVersion
    chatDeploymentName: chatDeploymentName
    embeddingDeploymentName: embeddingDeploymentName
    neo4jUri: 'bolt://${neo4j.outputs.fqdn}:${neo4jBoltPort}'
    neo4jUsername: neo4jUsername
    keyVaultUri: keyVaultUri
  }
}

module budget 'modules/budget.bicep' = {
  name: 'budget'
  params: {
    budgetName: budgetName
    budgetAmount: budgetAmount
    budgetContactEmail: budgetContactEmail
    budgetStartDate: budgetStartDate
  }
}

output containerAppFqdn string = app.outputs.fqdn
output containerAppName string = app.outputs.name
output openAiEndpoint string = openAi.outputs.endpoint
output logAnalyticsName string = environment.outputs.logAnalyticsName
output acrLoginServer string = registry.outputs.loginServer

// So local scripts (src/graph/extract.py, dedupe.py, timeline.py, query.py)
// and .env can point at this instance the same way they pointed at Aura.
output neo4jUri string = 'bolt://${neo4j.outputs.fqdn}:${neo4jBoltPort}'
output neo4jUsername string = neo4jUsername

// Passwords are no longer deployment outputs — retrieve them via Key
// Vault's own audited access path instead of ARM deployment history:
//   az keyvault secret show --vault-name <name> --name neo4j-password --query value -o tsv
output keyVaultName string = keyVault.outputs.name
output keyVaultUri string = keyVaultUri
