# API Diff: 1.0.0 → 2.0.0

## Summary

- **Total changes:** 15
- **Breaking changes:** 8
- **Pending review:** 15

## ⚠ Breaking Changes

### New query parameter: status (required)

| Field | Change | Old | New |
|-------|--------|-----|-----|
| status | added | - | string |

### Response 200 fields added: items, page_info, total_count

| Field | Change | Old | New |
|-------|--------|-----|-----|
| items | added | - | array (required) |
| page_info | added | - | object |
| total_count | added | - | integer (required) |

### Response 200 fields removed: data, total

| Field | Change | Old | New |
|-------|--------|-----|-----|
| data | removed | array (required) | - |
| total | removed | integer (required) | - |

### Parameter path:id modified

| Field | Change | Old | New |
|-------|--------|-----|-----|
| id | modified | integer | string |

### Response 200 fields added: created_at, status

| Field | Change | Old | New |
|-------|--------|-----|-----|
| created_at | added | - | string (required) |
| status | added | - | string (required) |

### Response 200 fields removed: role

| Field | Change | Old | New |
|-------|--------|-----|-----|
| role | removed | string | - |

### Response 200 fields modified: id

| Field | Change | Old | New |
|-------|--------|-----|-----|
| id | modified | integer | string |
| id | modified | - | User UUID |

### Response 201 fields modified: id

| Field | Change | Old | New |
|-------|--------|-----|-----|
| id | modified | integer | string |

## auth

### 新增

- New endpoint added: POST /auth/token `[LOW]`

### 修改

- Endpoint metadata updated: POST /auth/login `[LOW]`
  - `description` (description): `Authenticate user and return token` → `Authenticate user and return token (deprecated)`

### 废弃

- Endpoint deprecated: POST /auth/login `[MEDIUM]`


## users

### 新增

- New endpoint added: PATCH /users/{id} `[LOW]`
- Request fields added: status `[LOW]`
  - `status`: `string`

### 修改

- Endpoint metadata updated: GET /users `[LOW]`
  - `summary` (summary): `List all users` → `List all users with filters`
  - `description` (description): `Returns a paginated list of users` → `Returns a paginated list of users with filtering support`
- Endpoint metadata updated: GET /users/{id} `[LOW]`
  - `description` (description): `Returns a single user` → `Returns a single user with extended profile`


## ⚠ Missing Examples

- `PATCH /users/{id}`
- `POST /auth/token`

## ⏳ Pending Review

- Endpoint metadata updated: GET /users
- New query parameter: status (required) **[BREAKING]**
- Response 200 fields added: items, page_info, total_count **[BREAKING]**
- Response 200 fields removed: data, total **[BREAKING]**
- Endpoint metadata updated: GET /users/{id}
- Parameter path:id modified **[BREAKING]**
- Response 200 fields added: created_at, status **[BREAKING]**
- Response 200 fields removed: role **[BREAKING]**
- Response 200 fields modified: id **[BREAKING]**
- New endpoint added: PATCH /users/{id}
- Endpoint deprecated: POST /auth/login
- Endpoint metadata updated: POST /auth/login
- New endpoint added: POST /auth/token
- Request fields added: status
- Response 201 fields modified: id **[BREAKING]**
