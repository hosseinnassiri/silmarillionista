// Azure Container Registry only. Pull/push role assignments live in
// rbac.bicep, since they also need principal IDs from app.bicep — keeping
// them here would create a circular module dependency.

param location string
param acrName string

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

output id string = acr.id
output loginServer string = acr.properties.loginServer
output name string = acr.name
