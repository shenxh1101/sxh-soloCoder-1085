# 2.0.0

> **Internal Release** - Channel: internal
> Released by: bob@example.com

_Released on 2026-06-09_

## Highlights

- Order v2 with pagination and payment methods
- Added PATCH /orders/{id} and POST /refunds

## BREAKING CHANGES

### Removed query parameter: page

| Field | Change | Old | New |
|-------|--------|-----|-----|
| page | removed | integer | - |

### Parameter query:status modified

| Field | Change | Old | New |
|-------|--------|-----|-----|
| status | modified | - | True |

### Response 200 fields added: items, next_cursor, total

| Field | Change | Old | New |
|-------|--------|-----|-----|
| items | added | - | array (required) |
| next_cursor | added | - | string |
| total | added | - | integer (required) |

### Response 200 fields removed: count, orders

| Field | Change | Old | New |
|-------|--------|-----|-----|
| count | removed | integer (required) | - |
| orders | removed | array (required) | - |

### Parameter path:id modified

| Field | Change | Old | New |
|-------|--------|-----|-----|
| id | modified | integer | string |

### Response 200 fields added: created_at, order_id, total_amount, user_uuid

| Field | Change | Old | New |
|-------|--------|-----|-----|
| created_at | added | - | string (required) |
| order_id | added | - | string (required) |
| total_amount | added | - | object (required) |
| user_uuid | added | - | string (required) |

### Response 200 fields removed: amount, id, user_id

| Field | Change | Old | New |
|-------|--------|-----|-----|
| amount | removed | number (required) | - |
| id | removed | integer (required) | - |
| user_id | removed | integer (required) | - |

### Request fields modified: method, order_id

| Field | Change | Old | New |
|-------|--------|-----|-----|
| method | modified | - | credit_card, alipay, wechat, crypto |
| order_id | modified | integer | string |

### Response 201 fields added: transaction_id

| Field | Change | Old | New |
|-------|--------|-----|-----|
| transaction_id | added | - | string (required) |

### Response 201 fields removed: payment_id

| Field | Change | Old | New |
|-------|--------|-----|-----|
| payment_id | removed | integer (required) | - |

## orders

### 新增

- New query parameter: cursor `[LOW]`
  - `cursor`: `string`
- New query parameter: limit `[LOW]`
  - `limit`: `integer`
- New endpoint added: PATCH /orders/{id} `[LOW]`

### 修改

- Endpoint metadata updated: GET /orders `[LOW]`
  - `summary` (summary): `List orders` -> `List orders with filters`
  - `description` (description): `List all orders with pagination` -> `List all orders with rich filtering`

## payments

### 新增

- Request fields added: currency `[LOW]`
  - `currency`: `string`
- New endpoint added: POST /refunds `[LOW]`

### 修改

- Endpoint metadata updated: POST /payments `[LOW]`
  - `summary` (summary): `Create payment` -> `Create payment (multi-method)`

---

## Pending Review

- [ ] Endpoint metadata updated: GET /orders
- [ ] New query parameter: cursor
- [ ] New query parameter: limit
- [ ] Removed query parameter: page **[BREAKING]**
- [ ] Parameter query:status modified **[BREAKING]**
- [ ] Response 200 fields added: items, next_cursor, total **[BREAKING]**
- [ ] Response 200 fields removed: count, orders **[BREAKING]**
- [ ] Parameter path:id modified **[BREAKING]**
- [ ] Response 200 fields added: created_at, order_id, total_amount, user_uuid **[BREAKING]**
- [ ] Response 200 fields removed: amount, id, user_id **[BREAKING]**
- [ ] New endpoint added: PATCH /orders/{id}
- [ ] Request fields modified: method, order_id **[BREAKING]**
- [ ] Response 201 fields added: transaction_id **[BREAKING]**
- [ ] Response 201 fields removed: payment_id **[BREAKING]**
