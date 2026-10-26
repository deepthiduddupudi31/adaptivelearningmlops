from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from jose import JWTError, jwt
from pwdlib import PasswordHash

from .config import settings
from .db import get_connection

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hash.verify(password, hashed)
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if not payload.get("sub"):
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication token. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError as exc:
        # Do not expose token contents or secret in the response.
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def current_user_from_request(request: Request):
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")

    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token.strip())

    with get_connection() as connection:
        user = connection.execute(
            "SELECT id, full_name, email FROM users WHERE id = %s",
            (payload["sub"],),
        ).fetchone()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User associated with this token was not found",
        )

    return {
        "id": str(user["id"]),
        "full_name": user["full_name"],
        "email": user["email"],
    }    



def get_current_user(request: Request):
    authorization = request.headers.get("Authorization", "")

    print("DEBUG request path:", request.url.path)
    print("DEBUG Authorization header present:", bool(authorization))
    print("DEBUG Authorization scheme:", authorization.partition(" ")[0] or "MISSING")

    scheme, _, token = authorization.partition(" ")

    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token.strip())
    with get_connection() as connection:
        user = connection.execute(
            "SELECT id, full_name, email FROM users WHERE id = %s",
            (payload["sub"],),
        ).fetchone()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User no longer exists. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "id": str(user["id"]),
        "full_name": user["full_name"],
        "email": user["email"],
    }
