# 2.0.0

_Released on 2026-06-10_

## Highlights

- Major version upgrade with breaking changes
- New OAuth2 /auth/token endpoint
- Added PATCH /users/{id} for partial updates

## auth

### 新增

- New endpoint added: POST /auth/token `[LOW]`

### 修改

- Endpoint metadata updated: POST /auth/login `[LOW]`
  - `description` (description): `Authenticate user and return token` -> `Authenticate user and return token (deprecated)`

### 废弃

- Endpoint deprecated: POST /auth/login `[MEDIUM]`
