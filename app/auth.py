from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import HTTPException, Request, Response
from psycopg import Connection

from app.config import settings

COOKIE_NAME = "sm27_session"


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def issue_session(conn: Connection, manager_id: str, response: Response) -> None:
    token = secrets.token_urlsafe(36)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn.execute(
        "UPDATE managers SET session_token_hash = %s, updated_at = now() WHERE id = %s",
        (token_hash, manager_id),
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(timedelta(days=settings.session_days).total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session(conn: Connection, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn.execute(
            "UPDATE managers SET session_token_hash = NULL, updated_at = now() WHERE session_token_hash = %s",
            (token_hash,),
        )
    response.delete_cookie(COOKIE_NAME, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")


def current_manager(request: Request, conn: Connection) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Требуется вход в аккаунт")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    manager = conn.execute(
        "SELECT id, manager_name, auth_subject FROM managers WHERE session_token_hash = %s",
        (token_hash,),
    ).fetchone()
    if not manager:
        raise HTTPException(status_code=401, detail="Сессия завершена. Войдите снова.")
    return dict(manager)
