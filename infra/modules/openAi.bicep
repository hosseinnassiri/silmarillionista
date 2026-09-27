param location string
param openAiAccountName string
param chatDeploymentName string
param chatModelName string
param chatModelVersion string
param chatModelCapacity int
param routerDeploymentName string
param routerModelName string
param routerModelVersion string
param routerModelCapacity int
param embeddingDeploymentName string
param embeddingModelVersion string
param embeddingModelCapacity int

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2026-07-01' = {
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

// The default policy blocks Violence at severity Medium — the Silmarillion
// is narrative battle/war content (Dagor Bragollach, the Kinslaying, the
// Fall of Gondolin, etc.), which routinely lands at exactly that severity
// and gets blocked outright even though it's literary text, not a request
// for real-world violent content. This custom policy is the same as
// Microsoft.DefaultV2 except Violence is raised to High (blocks only
// severe/extreme content); Hate/Sexual/Selfharm stay at the default Medium.
// Raising a threshold like this is self-service — no Limited Access
// approval needed, unlike disabling a category outright.
resource chatRaiPolicy 'Microsoft.CognitiveServices/accounts/raiPolicies@2026-07-01' = {
  parent: openAiAccount
  name: 'silmarillion-narrative'
  properties: {
    basePolicyName: 'Microsoft.DefaultV2'
    mode: 'Blocking'
    contentFilters: [
      { name: 'Hate', enabled: true, blocking: true, severityThreshold: 'Medium', source: 'Prompt' }
      { name: 'Hate', enabled: true, blocking: true, severityThreshold: 'Medium', source: 'Completion' }
      { name: 'Sexual', enabled: true, blocking: true, severityThreshold: 'Medium', source: 'Prompt' }
      { name: 'Sexual', enabled: true, blocking: true, severityThreshold: 'Medium', source: 'Completion' }
      { name: 'Violence', enabled: true, blocking: true, severityThreshold: 'High', source: 'Prompt' }
      { name: 'Violence', enabled: true, blocking: true, severityThreshold: 'High', source: 'Completion' }
      { name: 'Selfharm', enabled: true, blocking: true, severityThreshold: 'Medium', source: 'Prompt' }
      { name: 'Selfharm', enabled: true, blocking: true, severityThreshold: 'Medium', source: 'Completion' }
    ]
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-07-01' = {
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
    raiPolicyName: chatRaiPolicy.name
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-07-01' = {
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

// Cheap/fast deployment for router_node's 3-way classification only (see
// src/llm.py:get_router_llm()) — synthesis and Cypher generation stay on
// chatDeployment. Same RAI policy as chatDeployment: the router still sees
// the raw user question, so it needs the same Violence-severity override.
resource routerDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-07-01' = {
  parent: openAiAccount
  name: routerDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: routerModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: routerModelName
      version: routerModelVersion
    }
    raiPolicyName: chatRaiPolicy.name
  }
  dependsOn: [
    embeddingDeployment
  ]
}

output endpoint string = openAiAccount.properties.endpoint
output accountName string = openAiAccount.name
