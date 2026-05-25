"""
User Authentication & Parent Profiles
──────────────────────────────────────
JWT-based authentication with parent profiles.
Supports registration, login, profile management, and child management.
"""

import os
import hashlib
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from functools import wraps

import jwt
from flask import request, jsonify, g

logger = logging.getLogger('brave_story.auth')

_jwt_secret_env = os.environ.get('JWT_SECRET_KEY')
if _jwt_secret_env:
    SECRET_KEY = _jwt_secret_env
else:
    # In production, refuse to start without a stable secret — otherwise
    # every restart silently invalidates all tokens and multiple workers
    # would each sign with a different key.
    if os.environ.get('FLASK_DEBUG', '1') != '1' or os.environ.get('FLASK_ENV') == 'production':
        raise RuntimeError(
            'JWT_SECRET_KEY environment variable is required in production. '
            'Set it to a stable, random 32+ byte hex string.'
        )
    SECRET_KEY = secrets.token_hex(32)
    logger.warning('JWT_SECRET_KEY not set — generated an ephemeral dev secret. '
                   'All tokens will be invalidated on restart.')
TOKEN_EXPIRY_HOURS = int(os.environ.get('TOKEN_EXPIRY_HOURS', '72'))
ALGORITHM = 'HS256'


# ── Password hashing ──────────────────────────────────────────────────

def hash_password(password: str) -> Tuple[str, str]:
    """Hash password with random salt. Returns (hash, salt)."""
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
    return hashed.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify password against stored hash."""
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
    return hashed.hex() == stored_hash


# ── JWT Token management ─────────────────────────────────────────────

def create_token(user_id: int, email: str) -> str:
    """Create a JWT token for authenticated user."""
    payload = {
        'user_id': user_id,
        'email': email,
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.info('Token expired')
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f'Invalid token: {e}')
        return None


# ── Auth middleware ───────────────────────────────────────────────────
# CSRF note: Tokens are transmitted exclusively via the Authorization
# header (not cookies), so CSRF attacks cannot attach credentials
# automatically. No additional CSRF token mechanism is required.

def login_required(f):
    """Decorator to require authentication on routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization', '')

        if auth_header.startswith('Bearer '):
            token = auth_header[7:]

        if not token:
            return jsonify({'message': 'Authentication required'}), 401

        payload = decode_token(token)
        if not payload:
            return jsonify({'message': 'Invalid or expired token'}), 401

        g.user_id = payload['user_id']
        g.user_email = payload['email']
        return f(*args, **kwargs)

    return decorated


def optional_auth(f):
    """Decorator that sets g.user_id if token present, but doesn't require it."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization', '')

        if auth_header.startswith('Bearer '):
            token = auth_header[7:]

        if token:
            payload = decode_token(token)
            if payload:
                g.user_id = payload['user_id']
                g.user_email = payload['email']
            else:
                g.user_id = None
                g.user_email = None
        else:
            g.user_id = None
            g.user_email = None

        return f(*args, **kwargs)

    return decorated


# ── Validation ───────────────────────────────────────────────────────

def validate_registration(data: dict) -> Tuple[bool, str]:
    """Validate registration data."""
    email = data.get('email', '').strip()
    password = data.get('password', '')
    name = data.get('name', '').strip()

    if not email or '@' not in email or '.' not in email:
        return False, 'Valid email is required'
    if len(password) < 8:
        return False, 'Password must be at least 8 characters'
    if not name or len(name) < 2:
        return False, 'Name is required (minimum 2 characters)'
    if len(name) > 100:
        return False, 'Name is too long (max 100 characters)'

    return True, ''
