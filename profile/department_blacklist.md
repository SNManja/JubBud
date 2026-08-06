# Department Blacklist (Hard Initial Filter)

Positions whose department name, as provided by the job portal or API, matches any of the following excluded areas will be immediately discarded before LLM parsing or ranking.

This filter should only be applied to explicit department or team metadata. It should not inspect the full job description.

## Sales and Business Development

- sales
- business_development
- partnerships
- revenue
- revenue_operations
- commercial
- account_management

## Marketing and Communications

- marketing
- growth_marketing
- product_marketing
- communications
- public_relations
- content
- brand
- community

## Recruiting and Human Resources

- recruiting
- talent_acquisition
- human_resources
- hr
- people
- people_operations
- people_and_culture
- rrhh

## Finance and Accounting

- finance
- accounting
- billing
- treasury
- tax
- payroll
- accounts_payable
- accounts_receivable

## Legal, Compliance and Risk

- legal
- compliance
- risk
- fraud
- audit
- internal_audit
- information_governance

## Customer-Facing Non-Technical Areas

- customer_success
- customer_experience
- customer_service
- customer_care
- client_success
- merchant_support

## Business and Administrative Operations

- business_operations
- commercial_operations
- merchant_operations
- administrative
- administration
- procurement
- purchasing
- logistics
- operations specialist