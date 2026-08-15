// Azure Container Registry, plus the two data-plane role assignments scoped
// to it — kept together rather than centralized, since both grants are
// specifically about "who can push/pull this registry." Contributor (held
// by the deploy principal at the resource-group scope) doesn't cover either
// one: push/pull are ACR data-plane actions, separate from the control-plane
// rights needed to create/manage the registry resource itself.

param location string
param acrName string
param appPrincipalId string
param deployServicePrincipalObjectId string

resource acr 'Microsoft.ContainerRegistry/registries@2026-03-01-preview' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var acrPushRoleId = '8311e382-0749-4cb8-b61a-304f252e45ec'

// Lets the main app's managed identity pull at runtime — no stored
// credential, unlike the GHCR PAT approach this replaced.
resource acrPullForApp 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, appPrincipalId, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Lets deploy.yml's GitHub Actions service principal push new images.
resource acrPushForDeployPrincipal 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, deployServicePrincipalObjectId, acrPushRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPushRoleId)
    principalId: deployServicePrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}

output id string = acr.id
output loginServer string = acr.properties.loginServer
output name string = acr.name
