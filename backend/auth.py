"""Authentication: custom JWT email/password + Emergent-managed Google Auth."""
import os
import secrets
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt
import requests
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, EmailStr, Field

from core import db, new_id, now_iso, current_fy

router = APIRouter(prefix="/api/auth", tags=["auth"])
JWT_ALGORITHM = "HS256"
EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str) -> str:
    return jwt.encode({"sub": user_id, "email": email, "type": "access",
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
                      get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id, "type": "refresh",
                       "exp": datetime.now(timezone.utc) + timedelta(days=7)},
                      get_jwt_secret(), algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, access: str, refresh: str):
    response.set_cookie("access_token", access, httponly=True, secure=True,
                        samesite="none", max_age=900, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True,
                        samesite="none", max_age=604800, path="/")


async def create_default_business(user_id: str, name: str) -> str:
    business_id = new_id("biz")
    await db.businesses.insert_one({
        "business_id": business_id,
        "owner_user_id": user_id,
        "name": name,
        "abn": "",
        "gst_registered": True,
        "default_gst_rate": "0.10",
        "currency": "AUD",
        "timezone": "Australia/Adelaide",
        "locale": "en-AU",
        "is_demo": False,
        "created_at": now_iso(),
    })
    from seed import seed_default_setup
    await seed_default_setup(business_id)
    return business_id


async def _public_user(doc: dict) -> dict:
    return {
        "user_id": doc["user_id"],
        "email": doc["email"],
        "name": doc.get("name", ""),
        "picture": doc.get("picture"),
        "role": doc.get("role", "owner"),
        "auth_provider": doc.get("auth_provider", "password"),
        "business_ids": doc.get("business_ids", []),
        "default_business_id": doc.get("default_business_id"),
        "current_fy": current_fy(),
    }


# ---------- brute force ----------
async def check_lockout(identifier: str):
    rec = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    if rec and rec.get("locked_until"):
        until = datetime.fromisoformat(rec["locked_until"])
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if until > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")


async def register_failure(identifier: str):
    rec = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    count = (rec or {}).get("count", 0) + 1
    update = {"identifier": identifier, "count": count}
    if count >= 5:
        update["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        update["count"] = 0
    await db.login_attempts.update_one({"identifier": identifier}, {"$set": update}, upsert=True)


# ---------- models ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    business_name: str = Field(default="Urban Dotted", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


# ---------- endpoints ----------
@router.post("/register")
async def register(body: RegisterIn, response: Response):
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists")
    user_id = new_id("user")
    business_id = await create_default_business(user_id, body.business_name or "Urban Dotted")
    doc = {
        "user_id": user_id, "email": email, "name": body.name,
        "password_hash": hash_password(body.password), "auth_provider": "password",
        "role": "owner", "business_ids": [business_id], "default_business_id": business_id,
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    set_auth_cookies(response, create_access_token(user_id, email), create_refresh_token(user_id))
    return await _public_user(doc)


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.lower().strip()
    ident = f"{request.client.host if request.client else 'unknown'}:{email}"
    await check_lockout(ident)
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        await register_failure(ident)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await db.login_attempts.delete_one({"identifier": ident})
    set_auth_cookies(response, create_access_token(user["user_id"], email), create_refresh_token(user["user_id"]))
    return await _public_user(user)


@router.post("/session")
async def google_session(request: Request, response: Response):
    """Exchange Emergent Google Auth session_id for a persistent session cookie."""
    session_id = request.headers.get("X-Session-ID") or (await request.json()).get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id")
    try:
        r = requests.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": session_id}, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    email = (data.get("email") or "").lower().strip()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user_id = new_id("user")
        business_id = await create_default_business(user_id, "Urban Dotted")
        user = {
            "user_id": user_id, "email": email, "name": data.get("name", ""),
            "picture": data.get("picture"), "auth_provider": "google", "role": "owner",
            "business_ids": [business_id], "default_business_id": business_id,
            "created_at": now_iso(),
        }
        await db.users.insert_one(user)
    else:
        await db.users.update_one({"user_id": user["user_id"]},
                                  {"$set": {"picture": data.get("picture"), "name": data.get("name") or user.get("name")}})

    token = data.get("session_token") or secrets.token_urlsafe(32)
    await db.user_sessions.insert_one({
        "user_id": user["user_id"], "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": now_iso(),
    })
    response.set_cookie("session_token", token, httponly=True, secure=True,
                        samesite="none", max_age=604800, path="/")
    return await _public_user(user)


async def get_current_user(request: Request) -> dict:
    session_token = request.cookies.get("session_token")
    auth_header = request.headers.get("Authorization", "")
    bearer = auth_header[7:] if auth_header.startswith("Bearer ") else None

    for token in [session_token, bearer]:
        if not token:
            continue
        sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if sess:
            expires_at = sess["expires_at"]
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Session expired")
            user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0, "password_hash": 0})
            if user:
                return user

    token = request.cookies.get("access_token") or bearer
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_business_id(request: Request, user: dict = Depends(get_current_user)) -> str:
    """Tenant resolution + membership enforcement."""
    requested = request.headers.get("X-Business-Id") or request.query_params.get("business_id")
    allowed = user.get("business_ids", [])
    if requested:
        if requested not in allowed:
            raise HTTPException(status_code=403, detail="No access to this business")
        return requested
    if not allowed:
        raise HTTPException(status_code=400, detail="No business configured")
    return user.get("default_business_id") or allowed[0]


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return await _public_user(user)


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_many({"session_token": token})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    response.set_cookie("access_token", create_access_token(user["user_id"], user["email"]),
                        httponly=True, secure=True, samesite="none", max_age=900, path="/")
    return {"ok": True}


@router.post("/forgot-password")
async def forgot_password(body: ForgotIn):
    user = await db.users.find_one({"email": body.email.lower().strip()}, {"_id": 0})
    if user:
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": user["user_id"], "used": False,
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        })
        print(f"[password-reset] link: /reset-password?token={token}")
    return {"ok": True, "message": "If that email exists, a reset link has been generated."}


@router.post("/reset-password")
async def reset_password(body: ResetIn):
    rec = await db.password_reset_tokens.find_one({"token": body.token}, {"_id": 0})
    if not rec or rec.get("used"):
        raise HTTPException(status_code=400, detail="Invalid or used token")
    exp = rec["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expired")
    await db.users.update_one({"user_id": rec["user_id"]},
                              {"$set": {"password_hash": hash_password(body.password)}})
    await db.password_reset_tokens.update_one({"token": body.token}, {"$set": {"used": True}})
    return {"ok": True}


async def seed_admin():
    email = os.environ.get("ADMIN_EMAIL", "admin@urbandotted.com.au").lower()
    password = os.environ.get("ADMIN_PASSWORD", "UrbanDotted!2026")
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if not existing:
        user_id = new_id("user")
        business_id = await create_default_business(user_id, "Urban Dotted")
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": "Urban Dotted Admin",
            "password_hash": hash_password(password), "auth_provider": "password",
            "role": "owner", "business_ids": [business_id], "default_business_id": business_id,
            "created_at": now_iso(),
        })
    elif not verify_password(password, existing.get("password_hash") or ""):
        await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_password(password)}})
