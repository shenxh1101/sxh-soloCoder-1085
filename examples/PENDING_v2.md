# Pending Review Checklist

_Version: 2.0.0_

## Changes requiring confirmation

- [ ] Endpoint metadata updated: GET /users
- [ ] New query parameter: status (required) **[BREAKING]**
  - [ ] Add migration guide
- [ ] Response 200 fields added: items, page_info, total_count **[BREAKING]**
  - [ ] Add migration guide
- [ ] Response 200 fields removed: data, total **[BREAKING]**
  - [ ] Add migration guide
- [ ] Endpoint metadata updated: GET /users/{id}
- [ ] Parameter path:id modified **[BREAKING]**
  - [ ] Add migration guide
- [ ] Response 200 fields added: created_at, status **[BREAKING]**
  - [ ] Add migration guide
- [ ] Response 200 fields removed: role **[BREAKING]**
  - [ ] Add migration guide
- [ ] Response 200 fields modified: id **[BREAKING]**
  - [ ] Add migration guide
- [ ] New endpoint added: PATCH /users/{id}
- [ ] Endpoint deprecated: POST /auth/login
- [ ] Endpoint metadata updated: POST /auth/login
- [ ] New endpoint added: POST /auth/token
- [ ] Request fields added: status
- [ ] Response 201 fields modified: id **[BREAKING]**
  - [ ] Add migration guide

## Endpoints missing examples

- [ ] `PATCH /users/{id}`
- [ ] `POST /auth/token`
