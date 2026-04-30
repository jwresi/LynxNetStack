# Splynx API v2.0 - Key Endpoints Reference

**Base URL:** `http://YOUR_SPLYNX_DOMAIN/api/2.0/`
**Total Endpoints:** 549

## Authentication Endpoints (14 total)

### Core Authentication
- **POST** `/admin/auth/tokens` - Generate access token
- **GET** `/admin/auth/tokens/{token}` - Renew token  
- **DELETE** `/admin/auth/tokens/{token}` - Delete token
- **POST** `/admin/auth/sessions` - Create session
- **POST** `/admin/auth/trusted-devices` - Create trusted device
- **GET** `/admin/auth/trusted-devices` - List trusted devices
- **POST** `/admin/auth/two-factor-status` - Check 2FA status

### Portal Authentication
- **GET** `/portal/login/entry-points` - List entry points
- **POST** `/portal/login/two-factor-code` - Get 2FA code for portal
- **POST** `/portal/profile/reset-password-request` - Reset password request
- **POST** `/portal/profile/reset-password-confirm` - Confirm password reset

## Customer Management Endpoints (102 total)

### Customer CRUD
- **POST** `/admin/customers/customers` - Create customer
- **GET** `/admin/customers/customers` - List all customers
- **GET** `/admin/customers/customers/{id}` - Retrieve customer
- **PUT** `/admin/customers/customers/{id}` - Update customer
- **DELETE** `/admin/customers/customers/{id}` - Delete customer

### Customer Information
- **GET** `/admin/customers/customer-info/{id}` - Get customer info
- **PUT** `/admin/customers/customer-info/{id}` - Update customer info
- **GET** `/admin/customers/customer-billing-info/{id}` - Get billing info
- **PUT** `/admin/customers/customer-billing-info/{id}` - Update billing info

### Customer Services Control
- **PUT** `/admin/customers/customer/{customer_id}/internet-services--{service_id}?action=start` - Start internet service
- **PUT** `/admin/customers/customer/{customer_id}/internet-services--{service_id}?action=stop` - Stop internet service
- **PUT** `/admin/customers/customer/{customer_id}/voice-services--{service_id}?action=start` - Start voice service
- **PUT** `/admin/customers/customer/{customer_id}/voice-services--{service_id}?action=stop` - Stop voice service

### Customer Search & Statistics
- **GET** `/admin/customers/customers-search` - Search customers
- **GET** `/admin/customers/customer-statistics` - Total statistics
- **GET** `/admin/customers/customer-statistics/{id}` - Individual customer stats

## Billing & Finance Endpoints (66 total)

### Invoices
- **POST** `/admin/finance/invoices` - Create invoice
- **GET** `/admin/finance/invoices` - List all invoices
- **GET** `/admin/finance/invoices/{id}` - Retrieve invoice
- **PUT** `/admin/finance/invoices/{id}` - Update invoice
- **DELETE** `/admin/finance/invoices/{id}` - Delete invoice

### Payments
- **POST** `/admin/finance/payments` - Create payment
- **GET** `/admin/finance/payments` - List all payments
- **GET** `/admin/finance/payments/{id}` - Retrieve payment
- **PUT** `/admin/finance/payments/{id}` - Update payment
- **DELETE** `/admin/finance/payments/{id}` - Delete payment

### Transactions
- **POST** `/admin/finance/transactions` - Create transaction
- **GET** `/admin/finance/transactions` - List all transactions
- **GET** `/admin/finance/transactions/{id}` - Retrieve transaction
- **PUT** `/admin/finance/transactions/{id}` - Update transaction
- **DELETE** `/admin/finance/transactions/{id}` - Delete transaction

### Payment Methods
- **POST** `/admin/finance/payment-methods` - Create payment method
- **GET** `/admin/finance/payment-methods` - List payment methods
- **GET** `/admin/finance/payment-methods/{id}` - Retrieve payment method
- **PUT** `/admin/finance/payment-methods/{id}` - Update payment method
- **DELETE** `/admin/finance/payment-methods/{id}` - Delete payment method

## Tariffs & Pricing Endpoints (28 total)

### Internet Tariffs
- **POST** `/admin/tariffs/internet` - Create internet tariff
- **GET** `/admin/tariffs/internet` - List internet tariffs
- **GET** `/admin/tariffs/internet/{id}` - Retrieve internet tariff
- **PUT** `/admin/tariffs/internet/{id}` - Update internet tariff
- **DELETE** `/admin/tariffs/internet/{id}` - Delete internet tariff

### Voice Tariffs
- **POST** `/admin/tariffs/voice` - Create voice tariff
- **GET** `/admin/tariffs/voice` - List voice tariffs
- **GET** `/admin/tariffs/voice/{id}` - Retrieve voice tariff
- **PUT** `/admin/tariffs/voice/{id}` - Update voice tariff
- **DELETE** `/admin/tariffs/voice/{id}` - Delete voice tariff

### Bundle Tariffs
- **POST** `/admin/tariffs/bundle` - Create bundle tariff
- **GET** `/admin/tariffs/bundle` - List bundle tariffs
- **GET** `/admin/tariffs/bundle/{id}` - Retrieve bundle tariff
- **PUT** `/admin/tariffs/bundle/{id}` - Update bundle tariff
- **DELETE** `/admin/tariffs/bundle/{id}` - Delete bundle tariff

## Services Management Endpoints (23 total)

### Internet Services
- **POST** `/admin/customers/customer/{customer_id}/internet-services` - Create internet service
- **GET** `/admin/customers/customer/{customer_id}/internet-services` - List internet services
- **GET** `/admin/customers/customer/{customer_id}/internet-services--{service_id}` - Retrieve internet service
- **PUT** `/admin/customers/customer/{customer_id}/internet-services--{service_id}` - Update internet service
- **DELETE** `/admin/customers/customer/{customer_id}/internet-services--{service_id}` - Delete internet service

### Voice Services
- **POST** `/admin/customers/customer/{customer_id}/voice-services` - Create voice service
- **GET** `/admin/customers/customer/{customer_id}/voice-services` - List voice services
- **GET** `/admin/customers/customer/{customer_id}/voice-services--{service_id}` - Retrieve voice service
- **PUT** `/admin/customers/customer/{customer_id}/voice-services--{service_id}` - Update voice service
- **DELETE** `/admin/customers/customer/{customer_id}/voice-services--{service_id}` - Delete voice service

## Network & Infrastructure Endpoints (61 total)

### Routers
- **POST** `/admin/networking/routers` - Create router
- **GET** `/admin/networking/routers` - List routers
- **GET** `/admin/networking/routers/{id}` - Retrieve router
- **PUT** `/admin/networking/routers/{id}` - Update router
- **DELETE** `/admin/networking/routers/{id}` - Delete router

### IPv4 Networks
- **POST** `/admin/networking/ipv4-networks` - Create IPv4 network
- **GET** `/admin/networking/ipv4-networks` - List IPv4 networks
- **GET** `/admin/networking/ipv4-networks/{id}` - Retrieve IPv4 network
- **PUT** `/admin/networking/ipv4-networks/{id}` - Update IPv4 network
- **DELETE** `/admin/networking/ipv4-networks/{id}` - Delete IPv4 network

### IPv6 Networks
- **POST** `/admin/networking/ipv6-networks` - Create IPv6 network
- **GET** `/admin/networking/ipv6-networks` - List IPv6 networks
- **GET** `/admin/networking/ipv6-networks/{id}` - Retrieve IPv6 network
- **PUT** `/admin/networking/ipv6-networks/{id}` - Update IPv6 network
- **DELETE** `/admin/networking/ipv6-networks/{id}` - Delete IPv6 network

## CRM Endpoints (24 total)

### Leads
- **POST** `/admin/crm/leads` - Create lead
- **GET** `/admin/crm/leads` - List leads
- **GET** `/admin/crm/leads/{id}` - Retrieve lead
- **PUT** `/admin/crm/leads/{id}` - Update lead
- **DELETE** `/admin/crm/leads/{id}` - Delete lead
- **PUT** `/admin/crm/leads/{id}--convert-to-customer-simple` - Convert lead to customer

### Quotes
- **POST** `/admin/crm/quotes` - Create quote
- **GET** `/admin/crm/quotes` - List quotes
- **GET** `/admin/crm/quotes/{id}` - Retrieve quote
- **PUT** `/admin/crm/quotes/{id}` - Update quote
- **DELETE** `/admin/crm/quotes/{id}` - Delete quote

## Support & Tickets Endpoints (25 total)

### Tickets
- **POST** `/admin/support/tickets` - Create ticket
- **GET** `/admin/support/tickets` - List tickets
- **GET** `/admin/support/tickets/{id}` - Retrieve ticket
- **PUT** `/admin/support/tickets/{id}` - Update ticket
- **DELETE** `/admin/support/tickets/{id}` - Delete ticket

### Ticket Messages
- **POST** `/admin/support/ticket-messages` - Create ticket message
- **GET** `/admin/support/ticket-messages` - List ticket messages
- **GET** `/admin/support/ticket-messages/{id}` - Retrieve ticket message
- **PUT** `/admin/support/ticket-messages/{id}` - Update ticket message
- **DELETE** `/admin/support/ticket-messages/{id}` - Delete ticket message

## Authentication Requirements

All API endpoints require authentication via one of these methods:

1. **Basic Authentication** (requires "Unsecure access" enabled)
   ```
   Authorization: Basic <base64(api_key:api_secret)>
   ```

2. **Signature Authentication**
   ```
   Authorization: Splynx-EA (key=<key>&nonce=<nonce>&signature=<signature>)
   ```

3. **Access Token** (recommended)
   ```
   Authorization: Splynx-EA access-token=<token>
   ```

## Common Request/Response Patterns

### Standard List Response
```json
{
  "data": [...],
  "meta": {
    "total_count": 100,
    "count": 20,
    "limit": 20,
    "offset": 0
  }
}
```

### Standard Error Response
```json
{
  "message": "Error description",
  "code": 400,
  "internal_code": 1001
}
```

### Standard Success Response
```json
{
  "message": "Success",
  "data": {...}
}
```

## Query Parameters

Most list endpoints support:
- `limit` - Number of records to return
- `offset` - Number of records to skip
- `order` - Sort order (field_name:asc|desc)
- `search` - Search term
- Various filter parameters specific to each endpoint

Complete endpoint documentation with parameters and examples is available in the full API blueprint file.