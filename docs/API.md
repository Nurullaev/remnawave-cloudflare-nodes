# HTTP API

The service exposes an optional REST API for managing `config.yml` at runtime without restarting the container. All
changes are written to disk immediately and take effect on the next monitoring cycle.

Swagger UI is available at `http://<host>:<port>/api/docs` when both the API and `api.docs` are enabled.

## Setup

**`config.yml`**

```yaml
api:
  enabled: true
  host: "0.0.0.0"
  port: 8741
  docs: false  # set to true to enable Swagger UI at /api/docs
```

**`.env`**

```env
# Generate with: openssl rand -hex 32
API_TOKEN=your64charhextoken
```

If `API_TOKEN` is missing or not a 64-character lowercase hex string the service will refuse to start.

---

## Authentication

Every request must include the `X-API-Key` header:

```
X-API-Key: <your API token>
```

Any request with a missing or wrong token returns `401 Unauthorized`.

---

## Apex (root) domain zones

Use `"name": "@"` in zone objects to create A records for the root domain (`example.com`) instead of a subdomain.
When referencing an apex zone in URL path parameters (`PATCH` / `DELETE` zone endpoints), the `@` character must be
URL-encoded as `%40`:

```
# Subdomain zone
PATCH /api/config/domains/example.com/zones/s1

# Apex zone
PATCH /api/config/domains/example.com/zones/%40
```

---

## Zone node formats

Zones support two formats for specifying which nodes to monitor.

**`ips` — simple list of IPs**

```json
{
  "name": "s1",
  "ttl": 60,
  "ips": [
    "1.2.3.4",
    "5.6.7.8"
  ]
}
```

Each IP is both written to Cloudflare DNS and used to look up the node in Remnawave.

**`nodes` — advanced with separate addresses**

```json
{
  "name": "s1",
  "ttl": 60,
  "nodes": [
    {
      "ip": "1.2.3.4",
      "address": "100.64.0.1"
    },
    {
      "ip": "5.6.7.8",
      "address": "100.64.0.2"
    }
  ]
}
```

- `ip` — the value written to Cloudflare DNS.
- `address` — the `node.address` used to find the node in Remnawave (e.g. a Tailscale IP). When omitted, defaults to
  `ip`.

Both formats can be used within the same zone or across different zones.

---

## Endpoints

### GET `/api/config`

Returns the current configuration (no secrets are exposed).

**Response**

```json
{
  "check_interval": 30,
  "log_level": "INFO",
  "domains": [
    {
      "domain": "example.com",
      "zones": [
        {
          "name": "s1",
          "ttl": 60,
          "proxied": false,
          "ips": [
            "1.2.3.4"
          ]
        }
      ]
    }
  ],
  "telegram": {
    "enabled": false,
    "locale": "en",
    "notify": {
      "dns_changes": true,
      "node_changes": true,
      "errors": true,
      "critical": true
    }
  }
}
```

---

### PATCH `/api/config`

Update global settings. All fields are optional — only provided fields are changed.

**Request body**

```json
{
  "check_interval": 60,
  "log_level": "DEBUG",
  "telegram": {
    "enabled": true,
    "locale": "ru",
    "notify": {
      "dns_changes": true,
      "node_changes": false,
      "errors": true,
      "critical": true
    }
  }
}
```

| Field               | Type    | Constraints                         |
|---------------------|---------|-------------------------------------|
| `check_interval`    | integer | `>= 5`                              |
| `log_level`         | string  | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `telegram.enabled`  | boolean |                                     |
| `telegram.locale`   | string  | `en`, `ru`                          |
| `telegram.notify.*` | boolean |                                     |

**Response**

```json
{
  "status": "ok"
}
```

---

### GET `/api/config/domains`

Returns the list of all configured domains and their zones.

**Response**

```json
[
  {
    "domain": "example.com",
    "zones": [
      {
        "name": "s1",
        "ttl": 60,
        "proxied": false,
        "ips": [
          "1.2.3.4",
          "5.6.7.8"
        ]
      }
    ]
  }
]
```

---

### POST `/api/config/domains`

Add a new domain with one or more zones.

**Request body**

```json
{
  "domain": "example.com",
  "zones": [
    {
      "name": "s1",
      "ttl": 60,
      "proxied": false,
      "ips": [
        "1.2.3.4",
        "5.6.7.8"
      ]
    },
    {
      "name": "s2",
      "ttl": 60,
      "proxied": false,
      "nodes": [
        {
          "ip": "9.10.11.12",
          "address": "100.64.0.1"
        }
      ]
    },
    {
      "name": "@",
      "ttl": 60,
      "proxied": false,
      "ips": [
        "1.2.3.4"
      ]
    }
  ]
}
```

| Field                     | Type    | Constraints                                   |
|---------------------------|---------|-----------------------------------------------|
| `domain`                  | string  | required                                      |
| `zones`                   | array   | at least 1 zone                               |
| `zones[].name`            | string  | required; use `"@"` for apex/root DNS records |
| `zones[].ttl`             | integer | `>= 1`, default `120`                         |
| `zones[].proxied`         | boolean | default `false`                               |
| `zones[].ips`             | array   | list of IPs (simple format)                   |
| `zones[].nodes`           | array   | list of node objects (advanced format)        |
| `zones[].nodes[].ip`      | string  | required; IP written to Cloudflare DNS        |
| `zones[].nodes[].address` | string  | node address in Remnawave; defaults to `ip`   |

At least one of `ips` or `nodes` must be provided per zone.

**Response** — `201 Created`

```json
{
  "status": "ok"
}
```

**Errors**

| Code  | Reason                |
|-------|-----------------------|
| `409` | Domain already exists |

---

### DELETE `/api/config/domains/{domain}`

Remove a domain and all its zones.

```
DELETE /api/config/domains/example.com
```

**Response**

```json
{
  "status": "ok"
}
```

**Errors**

| Code  | Reason           |
|-------|------------------|
| `404` | Domain not found |

---

### POST `/api/config/domains/{domain}/zones`

Add a zone to an existing domain.

```
POST /api/config/domains/example.com/zones
```

**Request body**

```json
{
  "name": "s2",
  "ttl": 60,
  "proxied": false,
  "nodes": [
    {
      "ip": "9.10.11.12",
      "address": "100.64.0.1"
    }
  ]
}
```

**Response** — `201 Created`

```json
{
  "status": "ok"
}
```

**Errors**

| Code  | Reason              |
|-------|---------------------|
| `404` | Domain not found    |
| `409` | Zone already exists |

---

### PATCH `/api/config/domains/{domain}/zones/{zone_name}`

Update an existing zone. All fields are optional.

```
PATCH /api/config/domains/example.com/zones/s1
```

> **Apex zones:** Use `%40` (URL-encoded `@`) in the path when targeting the apex zone:
> ```
> PATCH /api/config/domains/example.com/zones/%40
> ```

**Request body**

```json
{
  "ttl": 120,
  "proxied": false,
  "ips": [
    "1.2.3.4",
    "5.6.7.8",
    "9.10.11.12"
  ]
}
```

| Field             | Type    | Constraints                                 |
|-------------------|---------|---------------------------------------------|
| `ttl`             | integer | `>= 1`                                      |
| `proxied`         | boolean |                                             |
| `ips`             | array   | at least 1 IP (replaces all existing IPs)   |
| `nodes`           | array   | list of node objects (replaces all nodes)   |
| `nodes[].ip`      | string  | required; IP written to Cloudflare DNS      |
| `nodes[].address` | string  | node address in Remnawave; defaults to `ip` |

**Response**

```json
{
  "status": "ok"
}
```

**Errors**

| Code  | Reason                   |
|-------|--------------------------|
| `404` | Domain or zone not found |

---

### DELETE `/api/config/domains/{domain}/zones/{zone_name}`

Remove a zone from a domain.

```
DELETE /api/config/domains/example.com/zones/s1
```

> **Apex zones:** Use `%40` (URL-encoded `@`) in the path when targeting the apex zone:
> ```
> DELETE /api/config/domains/example.com/zones/%40
> ```

**Response**

```json
{
  "status": "ok"
}
```

**Errors**

| Code  | Reason                   |
|-------|--------------------------|
| `404` | Domain or zone not found |

---

## Error responses

All error responses follow the same shape:

```json
{
  "detail": "Domain 'example.com' not found"
}
```

| Code  | Meaning                        |
|-------|--------------------------------|
| `401` | Invalid or missing `X-API-Key` |
| `404` | Resource not found             |
| `409` | Resource already exists        |
| `422` | Request body validation failed |
