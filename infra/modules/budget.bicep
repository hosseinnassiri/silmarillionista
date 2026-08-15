// Monthly cost guardrail. No dependencies on any other module.

param budgetName string
param budgetAmount int
param budgetContactEmail string
param budgetStartDate string

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
