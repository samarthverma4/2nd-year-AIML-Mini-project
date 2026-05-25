"""
Subscription Access Decorators
──────────────────────────────
Decorators that gate routes by tier, feature, or monthly usage.
All assume `@login_required` has already populated `g.user_id`.
"""

from functools import wraps
from flask import jsonify, g

from subscription_service import (
    check_limit, has_feature, get_user_tier, VALID_TIERS,
)
import database_v2 as db


def _is_admin() -> bool:
    try:
        return bool(db.is_user_admin(g.user_id))
    except Exception:
        return False


def require_tier(*tiers):
    """Allow only users on one of the listed tiers (e.g. 'caregiver', 'hospital')."""
    for t in tiers:
        if t not in VALID_TIERS:
            raise ValueError(f'Invalid tier in require_tier: {t}')

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if _is_admin():
                return fn(*args, **kwargs)
            tier = get_user_tier(g.user_id)
            if tier not in tiers:
                return jsonify({
                    'message': f'This feature requires a {" or ".join(tiers)} subscription.',
                    'current_tier': tier,
                    'required_tiers': list(tiers),
                    'upgrade_required': True,
                }), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_feature(feature: str):
    """Gate a route on a tier feature flag (e.g. 'face_api', 'multilingual_tts')."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if _is_admin():
                return fn(*args, **kwargs)
            if not has_feature(g.user_id, feature):
                return jsonify({
                    'message': f'This feature ({feature}) is not included in your current plan.',
                    'feature': feature,
                    'current_tier': get_user_tier(g.user_id),
                    'upgrade_required': True,
                }), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def check_usage_limit(resource: str):
    """Block the request if the user has hit their monthly cap for `resource`.

    Resources: 'storybook' | 'child_profile'.
    Routes are responsible for calling `increment_usage` after success
    (only meaningful for 'storybook' — child profiles are counted live).
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if _is_admin():
                return fn(*args, **kwargs)
            allowed, reason = check_limit(g.user_id, resource)
            if not allowed:
                return jsonify({
                    'message': reason,
                    'resource': resource,
                    'current_tier': get_user_tier(g.user_id),
                    'upgrade_required': True,
                }), 429
            return fn(*args, **kwargs)
        return wrapper
    return decorator
