# 2.0.0

_Released on 2026-06-10_

## Highlights

- Major version upgrade with breaking changes
- New OAuth2 /auth/token endpoint
- Added PATCH /users/{id} for partial updates

## BREAKING CHANGES

### New query parameter: status (required)

| Field | Change | Old | New |
|-------|--------|-----|-----|
| status | added | - | string |

**Migration guide:** Add status=active query parameter to all GET /users requests

### Response 200 fields added: items, page_info, total_count

| Field | Change | Old | New |
|-------|--------|-----|-----|
| items | added | - | array (required) |
| page_info | added | - | object |
| total_count | added | - | integer (required) |

**Migration guide:** Map new response fields: items replaces data, total_count replaces total

### Response 200 fields removed: data, total

| Field | Change | Old | New |
|-------|--------|-----|-----|
| data | removed | array (required) | - |
| total | removed | integer (required) | - |

**Migration guide:** Rename data to items and total to total_count in response parsing

### Parameter path:id modified

| Field | Change | Old | New |
|-------|--------|-----|-----|
| id | modified | integer | string |

**Migration guide:** Change user ID parameter from integer to UUID string

### Response 200 fields added: created_at, status

| Field | Change | Old | New |
|-------|--------|-----|-----|
| created_at | added | - | string (required) |
| status | added | - | string (required) |

**Migration guide:** Parse new status and created_at fields from response

### Response 200 fields removed: role

| Field | Change | Old | New |
|-------|--------|-----|-----|
| role | removed | string | - |

**Migration guide:** Remove role field parsing, use status instead

### Response 200 fields modified: id

| Field | Change | Old | New |
|-------|--------|-----|-----|
| id | modified | integer | string |
| id | modified | - | User UUID |

**Migration guide:** Update id field type from integer to string (UUID)

### Response 201 fields modified: id

| Field | Change | Old | New |
|-------|--------|-----|-----|
| id | modified | integer | string |

**Migration guide:** Update id field parsing from integer to string UUID

## auth

### 新增

- New endpoint added: POST /auth/token `[LOW]`

### 修改

- Endpoint metadata updated: POST /auth/login `[LOW]`
  - `description` (description): `Authenticate user and return token` -> `Authenticate user and return token (deprecated)`

### 废弃

- Endpoint deprecated: POST /auth/login `[MEDIUM]`

## users

### 新增

- New endpoint added: PATCH /users/{id} `[LOW]`
- Request fields added: status `[LOW]`
  - `status`: `string`

### 修改

- Endpoint metadata updated: GET /users `[LOW]`
  - `summary` (summary): `List all users` -> `List all users with filters`
  - `description` (description): `Returns a paginated list of users` -> `Returns a paginated list of users with filtering support`
- Endpoint metadata updated: GET /users/{id} `[LOW]`
  - `description` (description): `Returns a single user` -> `Returns a single user with extended profile`
