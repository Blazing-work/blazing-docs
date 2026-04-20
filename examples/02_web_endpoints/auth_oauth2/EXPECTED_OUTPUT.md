# Expected Output: OAuth2 Authentication

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

## OAuth2 Flow Overview

OAuth2 is a more complex authentication flow than API keys or JWT:

1. **Authorization Request**: User is redirected to OAuth2 provider's authorization page
2. **User Consent**: User grants permission to your application
3. **Authorization Code**: Provider redirects back with authorization code
4. **Token Exchange**: Your application exchanges code for access token
5. **API Request**: Client includes access token in Authorization header
6. **Token Validation**: Server validates token (via introspection or UserInfo endpoint)
7. **Request Processing**: If valid, request proceeds with user context

## Obtaining a Test Token

### Using Google OAuth2

1. Create OAuth2 credentials at [Google Cloud Console](https://console.cloud.google.com/)
2. Use OAuth2 Playground or implement authorization flow
3. Exchange authorization code for access token

Example using `httpx`:

```python
import httpx

# After getting authorization code
response = httpx.post(
    "https://oauth2.googleapis.com/token",
    data={
        "code": "authorization_code_here",
        "client_id": "your-client-id",
        "client_secret": "your-client-secret",
        "redirect_uri": "http://localhost:8080/callback",
        "grant_type": "authorization_code",
    }
)
token_data = response.json()
access_token = token_data["access_token"]
```

### Using Custom OAuth2 Provider

Configure your OAuth2 provider with:
- Client ID and secret
- Redirect URI
- Token introspection endpoint
- Scopes required

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
curl -X POST http://localhost:8080/api/user-data
```

**Response (401 Unauthorized):**
```json
{
  "detail": "Not authenticated"
}
```

### 3. Protected Endpoint With Valid OAuth2 Token

```bash
curl -X POST http://localhost:8080/api/user-data \
  -H "Authorization: Bearer ya29.a0AfH6SMBx..."
```

**Response (200 OK):**
```json
{
  "message": "OAuth2 protected resource",
  "user_id": "user@example.com",
  "tenant_id": "client-id-123",
  "scopes": ["read", "write"],
  "claims": {
    "sub": "user@example.com",
    "aud": "client-id-123",
    "scope": "read write",
    "exp": 1612345678,
    "active": true
  },
  "auth_method": "oauth2"
}
```

### 4. Google OAuth2 Endpoint With Valid Token

```bash
curl -X POST http://localhost:8080/api/google-user \
  -H "Authorization: Bearer ya29.a0AfH6SMBx..."
```

**Response (200 OK):**
```json
{
  "message": "Google OAuth2 authenticated",
  "user_id": "user@gmail.com",
  "provider": "google",
  "claims": {
    "sub": "1234567890",
    "email": "user@gmail.com",
    "email_verified": true,
    "name": "John Doe",
    "picture": "https://..."
  }
}
```

### 5. Protected Endpoint With Expired Token

```bash
curl -X POST http://localhost:8080/api/user-data \
  -H "Authorization: Bearer expired-token"
```

**Response (401 Unauthorized):**
```json
{
  "detail": "Not authenticated"
}
```

## Notes

- **Token Introspection**: The server validates tokens by calling the OAuth2 provider's introspection endpoint
- **Built-in Providers**: Blazing supports Google, GitHub, and Okta out of the box
- **Scopes**: OAuth2 scopes control what resources the token can access
- **Token Lifetime**: Access tokens typically expire after 1 hour
- **Refresh Tokens**: Not shown in this example, but used to obtain new access tokens
- **Security**: Always use HTTPS in production for OAuth2 flows
- **Client Credentials**: Never expose client secrets in client-side code
- **Provider Configuration**: Each OAuth2 provider has different endpoint URLs and claim formats

## Provider-Specific Configuration

### Google
- Introspection URL: `https://oauth2.googleapis.com/tokeninfo`
- UserInfo URL: `https://openidconnect.googleapis.com/v1/userinfo`
- Scopes: `openid`, `email`, `profile`

### GitHub
- UserInfo URL: `https://api.github.com/user`
- Scopes: `read:user`, `user:email`

### Okta
- Introspection URL: `https://{domain}.okta.com/oauth2/v1/introspect`
- UserInfo URL: `https://{domain}.okta.com/oauth2/v1/userinfo`

## Token Format

OAuth2 access tokens can be:
- **Opaque tokens**: Random strings validated via introspection
- **JWT tokens**: Self-contained with claims (can be validated locally)

This example demonstrates both approaches:
- Token introspection (standard OAuth2)
- UserInfo endpoint (OpenID Connect extension)
