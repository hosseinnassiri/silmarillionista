// Key Vault (RBAC-authorization mode) holding the two secrets that used to
// be written as plaintext `value`s directly on the Container Apps: the
// Neo4j admin password and the Azure OpenAI key. Consumers (app.bicep,
// neo4j.bicep) reference these by keyVaultUrl + managed identity instead of
// inlining the value — see rbac.bicep for the Key Vault Secrets User grants
// that make that readable, and the Key Vault Secrets Officer self-grant
// that lets this deployment's own identity write the secrets below.
//
// The OpenAI key never crosses a module output/parameter boundary — this
// module takes the account's NAME and does its own existing-resource
// lookup + listKeys() internally, so only the account name (not the key)
// is ever passed between modules.

param location string
param keyVaultName string
param tenantId string
param openAiAccountName string
param neo4jUsername string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
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

resource neo4jPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
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
resource neo4jAuthSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'neo4j-auth'
  properties: {
    value: '${neo4jUsername}/${neo4jPasswordValue}'
  }
}

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: openAiAccountName
}

resource openAiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'azure-openai-api-key'
  properties: {
    value: openAiAccount.listKeys().key1
  }
}

output id string = keyVault.id
output vaultUri string = keyVault.properties.vaultUri
output name string = keyVault.name
