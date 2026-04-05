from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from backend.core.config import settings


pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fernet() -> Fernet:
    return Fernet(settings.encryption_key)


def encrypt_secret(raw: str) -> str:
    return _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted secret") from exc
