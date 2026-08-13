# Auth Testing Playbook — Urban Dotted Expense Book

Two coexisting auth methods.

## 1. Custom JWT email + password (primary for testing)
Credentials (also in `/app/memory/test_credentials.md`):
- Email: `admin@urbandotted.com.au`
- Password: `UrbanDotted!2026`

### MongoDB verification
```
mongosh --eval "
use('test_database');
db.users.findOne({email:'admin@urbandotted.com.au'}, {password_hash:1, user_id:1, business_ids:1});
db.users.getIndexes();
"
```
Verify: bcrypt hash starts `$2b$`, unique index on `users.email`, index on `login_attempts.identifier`.

### API
```
API=https://deploy-fix-145.preview.emergentagent.com
curl -s -c /tmp/c.txt -X POST $API/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@urbandotted.com.au","password":"UrbanDotted!2026"}'
curl -s -b /tmp/c.txt $API/api/auth/me
curl -s -b /tmp/c.txt "$API/api/dashboard?fy=FY2025-26"
```
Login sets httpOnly `access_token` + `refresh_token` cookies (Secure, SameSite=none).
`/api/auth/refresh` mints a new access cookie from the refresh cookie.
Bearer tokens are also accepted via `Authorization: Bearer <token>`.

### Brute force
5 consecutive bad passwords for the same ip+email → HTTP 429 for 15 minutes.
Only test this LAST (it locks the account for 15 min); or clear with
`mongosh --eval "use('test_database'); db.login_attempts.deleteMany({})"`.

## 2. Emergent-managed Google Auth
- Login page has `data-testid="google-login-btn"` → redirects to `auth.emergentagent.com`.
- Callback: `#session_id=...` is detected during render in `App.js` `Router()` via `useLocation().hash`
  and handled by `AuthCallback`, which POSTs to `/api/auth/session` with header `X-Session-ID`.
- Backend stores a 7-day `session_token` in `user_sessions` and sets it as an httpOnly cookie.
- Do NOT attempt a real Google OAuth flow in automation. Instead inject a session:
```
mongosh --eval "
use('test_database');
var u = db.users.findOne({email:'admin@urbandotted.com.au'});
var t = 'test_session_' + Date.now();
db.user_sessions.insertOne({user_id:u.user_id, session_token:t,
  expires_at:new Date(Date.now()+7*24*3600*1000), created_at:new Date()});
print('session_token: ' + t);
"
```
Then either `Authorization: Bearer <token>` for curl, or add a browser cookie:
```
await page.context.add_cookies([{ "name":"session_token","value":"<token>",
  "domain":"expense-hub-au.preview.emergentagent.com","path":"/","httpOnly":True,
  "secure":True,"sameSite":"None" }])
```

## Multi-tenant enforcement (must test)
Every business-owned endpoint resolves the tenant via `X-Business-Id` header, falling back to the
user's `default_business_id`. Passing a `business_id` the user does not own MUST return 403:
```
curl -s -b /tmp/c.txt -H "X-Business-Id: biz_doesnotexist" "$API/api/transactions" -o /dev/null -w "%{http_code}\n"   # expect 403
curl -s "$API/api/transactions" -o /dev/null -w "%{http_code}\n"                                                      # expect 401
```

## Cleanup
```
mongosh --eval "use('test_database'); db.user_sessions.deleteMany({session_token:/test_session/}); db.login_attempts.deleteMany({});"
```
