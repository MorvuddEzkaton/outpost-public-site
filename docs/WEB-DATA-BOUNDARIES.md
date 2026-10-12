# OutPOSt Web Data Boundaries

**Phase:** Web Architecture Phase 0 v0.1
**Date:** 2026-08-16
**Priority:** Hard privacy and architectural constraints

## 1. Public website

May contain:
- public marketing content;
- product features;
- prices;
- downloads;
- changelog;
- SEO pages;
- public support/question form;
- documentation links.

Must not contain:
- customer store financial data;
- customer sales;
- private license secrets;
- signing keys;
- PRRO private keys;
- admin-only data.

## 2. Customer cabinet

The customer cabinet may display data belonging to that authenticated customer.

Allowed examples:
- customer's stores;
- customer's devices;
- customer's licenses;
- account binding;
- customer's own store statistics, where the product explicitly supports this;
- support/account actions.

Required rule:

```text
Customer A must never access Customer B data.
```

## 3. Admin

Hard project requirement:

`/admin` must NOT display customer-shop financial/sales content.

Forbidden in admin:
- turnover;
- sales amounts;
- receipt totals;
- item-level customer shop sales;
- product sales history;
- shop financial analytics.

Allowed in admin:
- customer identity/account management;
- license issuance;
- license history;
- license/key status;
- device management;
- account/store binding metadata;
- technical status;
- support/management functions.

## 4. Desktop sync boundary

Optional sync must be explicitly scoped.

Do not assume that because data exists in Desktop it should be uploaded.

Every sync entity must answer:

```text
Why is this data required in the cloud?
Who may read it?
How long is it retained?
Can Desktop work without it?
```

## 5. Licensing

Licensing services may know what is required to:
- issue licenses;
- bind licenses/devices/accounts;
- validate entitlement;
- maintain license history.

Licensing does not require customer sales/turnover data.

Keep entitlement data separate from shop financial data.

## 6. Support/public question

Current public flow:

```text
browser
  ↓
outpost.com.ua/api/public-question
  ↓
Pages _worker.js
  ↓
cabinet.outpost.com.ua/api/public-question
```

Security expectations:
- validation;
- honeypot;
- request-size protection;
- rate limiting;
- canonical Origin enforcement;
- no secret embedded in public JavaScript.

## 7. PRRO

Future own OutPOSt PRRO must be designed as a fiscal subsystem, not as a marketing-site feature.

Preferred flow:

```text
OutPOSt Desktop
      ↓
PRRO fiscal provider
      ↓
Official DPS API
```

Sensitive PRRO material:
- KEP/private signing material;
- fiscal payloads;
- receipt content;
- fiscal identifiers;
- offline fiscal state.

These must not be casually routed through the public website or exposed to `/admin`.

## 8. Local-first rule

Desktop core business data remains local-first.

Cloud services should extend the product, not silently become required for basic store operation.

## 9. Logging

Logs must avoid unnecessary storage of:
- full fiscal receipts;
- private keys;
- passwords;
- access tokens;
- raw financial payloads;
- customer personal data beyond diagnostic need.

Prefer:
- technical IDs;
- timestamps;
- result codes;
- correlation IDs;
- sanitized error messages.

## 10. Future architecture review gate

Any new web feature involving customer data must be classified before implementation:

```text
PUBLIC
CUSTOMER-PRIVATE
ADMIN-MANAGEMENT
TECHNICAL
FISCAL-SENSITIVE
SECRET
```

If classification is unclear, implementation should stop until the boundary is decided.
