// All cross-cutting role assignments in one place — each one grants a
// DATA-plane permission that Contributor (already held at the resource-group
// scope by the deploy service principal) deliberately doesn't include:
// Contributor manages resources, not who can access them or their data.
//
// The deploySP -> Key Vault Secrets Officer grant is a self-grant, made
// possible because the deploy SP already has User Access Administrator at
// the resource-group scope (granted once, manually, during bootstrap — see
// README). Because rbac.bicep necessarily runs after keyVault.bicep (it
// needs the vault's resource ID), the very FIRST deployment will predictably
// fail to write the two Key Vault secrets — the deploy SP doesn't have
// write access yet at that point in that same run. The role assignment
// below still gets created in that same run (it only needs the vault to
// exist, not the secrets), so a second `workflow_dispatch` re-run succeeds
// without any other change.

param acrId string
param keyVaultId string
param appPrincipalId string
param neo4jPrincipalId string
param deployServicePrincipalObjectId string

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var acrPushRoleId = '8311e382-0749-4cb8-b61a-304f252e45ec'
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
var keyVaultSecretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

resource acrScope 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: last(split(acrId, '/'))
}

resource keyVaultScope 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: last(split(keyVaultId, '/'))
}

// Lets the main app's managed identity pull from ACR at runtime — no stored
// credential, unlike the GHCR PAT approach this replaced.
resource acrPullForApp 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrId, appPrincipalId, acrPullRoleId)
  scope: acrScope
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Lets deploy.yml's GitHub Actions service principal push new images.
resource acrPushForDeployPrincipal 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrId, deployServicePrincipalObjectId, acrPushRoleId)
  scope: acrScope
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPushRoleId)
    principalId: deployServicePrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}

resource kvSecretsUserForApp 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVaultId, appPrincipalId, keyVaultSecretsUserRoleId)
  scope: keyVaultScope
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource kvSecretsUserForNeo4j 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVaultId, neo4jPrincipalId, keyVaultSecretsUserRoleId)
  scope: keyVaultScope
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: neo4jPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource kvSecretsOfficerForDeployPrincipal 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVaultId, deployServicePrincipalObjectId, keyVaultSecretsOfficerRoleId)
  scope: keyVaultScope
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsOfficerRoleId)
    principalId: deployServicePrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}
