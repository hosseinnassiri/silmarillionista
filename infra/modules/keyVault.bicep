// Key Vault (RBAC-authorization mode) holding the two secrets that used to
// be written as plaintext `value`s directly on the Container Apps: the
// Neo4j admin password/auth string and the Azure OpenAI key. Consumers
// (app.bicep, neo4j.bicep) reference these by keyVaultUrl + managed
// identity instead of inlining the value.
//
// The three role assignments below live here rather than centralized,
// since each is specifically about "who can read/write secrets in this
// vault." Contributor (held by the deploy principal at the resource-group
// scope) doesn't cover any of them — reading/writing secrets on an
// RBAC-authorization vault is a data-plane action.
//
// The OpenAI key never crosses a module output/parameter boundary — this
// module takes the account's NAME and does its own existing-resource
// lookup + listKeys() internally, so only the account name (not the key)
// is ever passed between modules.
//
// Because appPrincipalId/neo4jPrincipalId come from app.bicep/neo4j.bicep,
// and those modules get this vault's URI as a plain computed string from
// main.bicep (not this module's output) specifically to avoid a circular
// module dependency, this module structurally runs AFTER app/neo4j. The
// deploySP -> Key Vault Secrets Officer grant is a self-grant (made
// possible because the deploy SP already has User Access Administrator at
// the resource-group scope — see README's bootstrap section), and because
// it's created in the same deployment as the secrets it's needed to write,
// the very FIRST apply predictably fails on the secret-write step and needs
// one workflow_dispatch re-run — the role assignment itself still succeeds
// (it only needs the vault to exist), so the re-run succeeds without any
// other change.

param location string
param keyVaultName string
param tenantId string
param openAiAccountName string
param neo4jUsername string
param appPrincipalId string
param neo4jPrincipalId string
param deployServicePrincipalObjectId string

resource keyVault 'Microsoft.KeyVault/vaults@2026-03-01-preview' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: tenantId
    enableRbacAuthorization: true
  }
}

// Deterministic per resource group rather than random — Neo4j is only
// reachable over Bolt with this password (see neo4j.bicep's TCP ingress),
// so there's no external account/GitHub secret needed for it.
var neo4jPasswordValue = guid(resourceGroup().id, 'neo4j-admin-password')

resource neo4jPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2026-03-01-preview' = {
  parent: keyVault
  name: 'neo4j-password'
  properties: {
    value: neo4jPasswordValue
  }
}

// Container Apps secrets can't concatenate a keyVaultUrl-sourced value with
// a literal prefix, and Neo4j's own image expects NEO4J_AUTH as a single
// "user/password" string — so that pre-formatted string is stored as its
// own secret, derived from the same password, rather than composed at the
// Container App layer.
resource neo4jAuthSecret 'Microsoft.KeyVault/vaults/secrets@2026-03-01-preview' = {
  parent: keyVault
  name: 'neo4j-auth'
  properties: {
    value: '${neo4jUsername}/${neo4jPasswordValue}'
  }
}

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2026-05-15-preview' existing = {
  name: openAiAccountName
}

resource openAiKeySecret 'Microsoft.KeyVault/vaults/secrets@2026-03-01-preview' = {
  parent: keyVault
  name: 'azure-openai-api-key'
  properties: {
    value: openAiAccount.listKeys().key1
  }
}

var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
var keyVaultSecretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

resource kvSecretsUserForApp 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, appPrincipalId, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource kvSecretsUserForNeo4j 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, neo4jPrincipalId, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: neo4jPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource kvSecretsOfficerForDeployPrincipal 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, deployServicePrincipalObjectId, keyVaultSecretsOfficerRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsOfficerRoleId)
    principalId: deployServicePrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}

output id string = keyVault.id
output vaultUri string = keyVault.properties.vaultUri
output name string = keyVault.name
