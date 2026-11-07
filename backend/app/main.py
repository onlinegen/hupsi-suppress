"""HUPSI Suppress-Tool — E-Mail in Klaviyo suppressen.

Ein-Zweck-Tool für den Kunden HUPSI: E-Mail eingeben, Klick, Profil wird
im Klaviyo-Account suppressed. Passwort-Login (gemeinsames Passwort),
API-Key bleibt ausschließlich serverseitig.
"""
import asyncio
import hashlib
import hmac
import os
import re
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

APP_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = APP_DIR.parent.parent / "frontend"

PASSWORD = os.environ.get("HUPSI_PASSWORD", "test")
KLAVIYO_API_KEY = os.environ.get("KLAVIYO_API_KEY", "")
SESSION_SECRET = os.environ.get(
    "SESSION_SECRET",
    hashlib.sha256(("hupsi-suppress:" + PASSWORD).encode()).hexdigest(),
)
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "90"))
KLAVIYO_REVISION = "2025-07-15"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

app = FastAPI(title="HUPSI Suppress", docs_url=None, redoc_url=None, openapi_url=None)


# ---------------------------------------------------------------- Sessions
def _sign(expiry: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), ("session:" + expiry).encode(), hashlib.sha256).hexdigest()


def make_session_cookie() -> str:
    expiry = str(int(time.time()) + SESSION_DAYS * 86400)
    return expiry + "." + _sign(expiry)


def session_valid(cookie: Optional[str]) -> bool:
    if not cookie or "." not in cookie:
        return False
    expiry, sig = cookie.split(".", 1)
    if not expiry.isdigit() or int(expiry) < time.time():
        return False
    return hmac.compare_digest(sig, _sign(expiry))


def require_auth(request: Request) -> Optional[JSONResponse]:
    if session_valid(request.cookies.get("hupsi_session")):
        return None
    return JSONResponse({"detail": "Nicht angemeldet."}, status_code=401)


# ---------------------------------------------------------------- Modelle
class LoginBody(BaseModel):
    password: str


class SuppressBody(BaseModel):
    email: str


# Simple In-Memory-Bremse gegen Passwort-Raten (1 Worker, siehe Blaupause).
_login_fails = {"count": 0, "until": 0.0}


@app.post("/api/login")
def login(body: LoginBody, response: Response):
    now = time.time()
    if _login_fails["count"] >= 10 and now < _login_fails["until"]:
        return JSONResponse({"detail": "Zu viele Fehlversuche — bitte kurz warten."}, status_code=429)
    if not hmac.compare_digest(body.password, PASSWORD):
        _login_fails["count"] += 1
        _login_fails["until"] = now + 60
        return JSONResponse({"detail": "Falsches Passwort."}, status_code=401)
    _login_fails["count"] = 0
    response.set_cookie(
        "hupsi_session",
        make_session_cookie(),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("COOKIE_SECURE", "1") == "1",
    )
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("hupsi_session")
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return {"authenticated": session_valid(request.cookies.get("hupsi_session"))}


@app.post("/api/suppress")
async def suppress(body: SuppressBody, request: Request):
    denied = require_auth(request)
    if denied:
        return denied
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        return JSONResponse({"detail": "Das sieht nicht nach einer gültigen E-Mail-Adresse aus."}, status_code=422)
    if not KLAVIYO_API_KEY:
        return JSONResponse({"detail": "Server ist noch nicht konfiguriert (KLAVIYO_API_KEY fehlt)."}, status_code=500)

    payload = {
        "data": {
            "type": "profile-suppression-bulk-create-job",
            "attributes": {
                "profiles": {
                    "data": [
                        {"type": "profile", "attributes": {"email": email}}
                    ]
                }
            },
        }
    }
    headers = {
        "Authorization": "Klaviyo-API-Key " + KLAVIYO_API_KEY,
        "revision": KLAVIYO_REVISION,
        "Content-Type": "application/vnd.api+json",
        "Accept": "application/vnd.api+json",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                r = await client.post(
                    "https://a.klaviyo.com/api/profile-suppression-bulk-create-jobs",
                    json=payload,
                    headers=headers,
                )
            except httpx.HTTPError as exc:  # Netzwerkfehler → Retry
                last_exc = exc
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code in (200, 201, 202):
                return {"ok": True, "email": email}
            # Klartext-Fehler aus der Klaviyo-Antwort ziehen
            try:
                detail = r.json()["errors"][0].get("detail") or r.json()["errors"][0].get("title")
            except Exception:
                detail = r.text[:300]
            return JSONResponse(
                {"detail": "Klaviyo-Fehler (" + str(r.status_code) + "): " + str(detail)},
                status_code=502,
            )
        return JSONResponse({"detail": "Klaviyo nicht erreichbar: " + str(last_exc)}, status_code=502)


# ---------------------------------------------------------------- Frontend
@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
