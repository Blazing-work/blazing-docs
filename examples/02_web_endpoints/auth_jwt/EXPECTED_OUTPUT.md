# Expected Output: JWT Authentication

## Running the Example

```bash
python flow.py
```

Server starts on port 8080:

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

## Generating a Test JWT Token

To test this example, you need to generate a JWT token. Here's a Python snippet:

```python
import jwt

secret = "your-secret-key-here"
payload = {
    "sub": "user123",
    "app_id": "tenant-abc",
    "scopes": ["read", "write"],
    "aud": "my-api",
    "iss": "https://auth.example.com"
}
token = jwt.encode(payload, secret, algorithm="HS256")
print(f"Token: {token}")
```

For admin access, include `"admin"` in the scopes list.

## Testing the Endpoints

### 1. Public Endpoint (No Authentication)

```bash
curl -X POST http://localhost:8080/health
```

**Response (200 OK):**
```json
{
  "status": "healthy"
}
```

### 2. Protected Endpoint Without Token

```bash
curl -X POST http://localhost:8080/api/user/profile
```

**Response (401 Unauthorized):**
```json
{
  "detail": "Not authenticated"
}
```

### 3. Protected Endpoint With Valid JWT Token

```bash
curl -X POST http://localhost:8080/api/user/profile \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Response (200 OK):**
```json
{
  "user_id": "user123",
  "tenant_id": "tenant-abc",
  "scopes": ["read", "write"],
  "auth_method": "jwt",
  "profile": {
    "name": "John Doe",
    "email": "john@example.com"
  }
}
```

### 4. Admin Endpoint With User Token (No Admin Scope)

```bash
curl -X POST http://localhost:8080/api/admin/users \
  -H "Authorization: Bearer <token-without-admin-scope>"
```

**Response (200 OK - but insufficient permissions):**
```json
{
  "error": "Insufficient permissions"
}
```

### 5. Admin Endpoint With Admin Token

```bash
curl -X POST http://localhost:8080/api/admin/users \
  -H "Authorization: Bearer <token-with-admin-scope>"
```

**Response (200 OK):**
```json
{
  "users": [
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"}
  ],
  "authenticated_as": "user123"
}
```

### 6. Protected Endpoint With Invalid Token

```bash
curl -X POST http://localhost:8080/api/user/profile \
  -H "Authorization: Bearer invalid-token"
```

**Response (401 Unauthorized):**
```json
{
  "detail": "Not authenticated"
}
```

## Notes

- JWT tokens must include `sub` (user ID), `aud` (audience), and `iss` (issuer) claims
- The `app_id` claim is extracted as `tenant_id` by default
- The `scopes` claim can be a space-separated string or an array
- Token validation includes signature verification, expiration (if `exp` claim present), and claims validation
- In production, store the secret in environment variables, not in code
- Consider using public/private key pairs (RS256) instead of shared secrets (HS256) for production
- The token shown in examples is truncated for brevity - actual JWT tokens are much longer
