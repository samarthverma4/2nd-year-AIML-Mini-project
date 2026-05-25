"""
Subscription Service
────────────────────
Tier definitions, usage tracking, and access checks for the
Free / Caregiver / Hospital subscription model.

Storybook usage is tracked per calendar month (YYYY-MM).
Child profile limits are enforced against the live count of
rows in the children table — they are not monthly counters.
"""

import logging
from datetime import datetime, timezone
from typing import Tuple, Optional

import database_v2 as db
from database_v2 import get_db, _execute, _fetchone

logger = logging.getLogger('brave_story.subscription')


TIER_FREE = 'free'
TIER_CAREGIVER = 'caregiver'
TIER_HOSPITAL = 'hospital'
VALID_TIERS = (TIER_FREE, TIER_CAREGIVER, TIER_HOSPITAL)

# None = unlimited
TIER_LIMITS = {
    TIER_FREE:      {'storybooks': 3,    'child_profiles': 1},
    TIER_CAREGIVER: {'storybooks': 20,   'child_profiles': 3},
    TIER_HOSPITAL:  {'storybooks': None, 'child_profiles': None},
}

TIER_FEATURES = {
    TIER_FREE: {
        'multilingual_tts':  False,
        'pdf_export':        False,
        'face_api':          False,
        'custom_mood':       False,
        'analytics':         False,
        'custom_branding':   False,
    },
    TIER_CAREGIVER: {
        'multilingual_tts':  True,
        'pdf_export':        True,
        'face_api':          True,
        'custom_mood':       True,
        'analytics':         False,
        'custom_branding':   False,
    },
    TIER_HOSPITAL: {
        'multilingual_tts':  True,
        'pdf_export':        True,
        'face_api':          True,
        'custom_mood':       True,
        'analytics':         True,
        'custom_branding':   True,
    },
}

TIER_PRICING_PAISE = {
    TIER_FREE:      0,
    TIER_CAREGIVER: 29900,    # ₹299
    TIER_HOSPITAL:  499900,   # ₹4,999
}


def _current_month() -> str:
    """Return the current calendar month as 'YYYY-MM' (UTC)."""
    return datetime.now(timezone.utc).strftime('%Y-%m')


def get_user_tier(user_id: int) -> str:
    """Return the user's effective tier.

    If the subscription has expired, the tier is treated as 'free'
    regardless of what is stored.
    """
    with get_db() as conn:
        row = _fetchone(
            conn,
            'SELECT subscription_tier, subscription_expires_at, subscription_status FROM users WHERE id = ?',
            (user_id,),
        )
    if not row:
        return TIER_FREE

    d = dict(row) if not isinstance(row, dict) else row
    tier = (d.get('subscription_tier') or TIER_FREE).strip()
    if tier not in VALID_TIERS:
        return TIER_FREE

    expires = d.get('subscription_expires_at')
    if tier != TIER_FREE and expires:
        try:
            exp_dt = datetime.fromisoformat(str(expires).replace('Z', '+00:00'))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < datetime.now(timezone.utc):
                return TIER_FREE
        except (ValueError, TypeError):
            logger.warning('Invalid subscription_expires_at for user %s: %r', user_id, expires)

    return tier


def has_feature(user_id: int, feature: str) -> bool:
    """Check if the user's tier includes a specific feature."""
    return TIER_FEATURES.get(get_user_tier(user_id), {}).get(feature, False)


def get_usage(user_id: int) -> dict:
    """Return current-month storybook count + live child profile count."""
    month = _current_month()
    with get_db() as conn:
        row = _fetchone(
            conn,
            'SELECT storybooks_generated FROM usage_counters WHERE user_id = ? AND month = ?',
            (user_id, month),
        )
        storybooks = 0
        if row:
            d = dict(row) if not isinstance(row, dict) else row
            storybooks = int(d.get('storybooks_generated') or 0)

        prof_row = _fetchone(
            conn,
            'SELECT COUNT(*) AS c FROM children WHERE user_id = ?',
            (user_id,),
        )
        profiles = 0
        if prof_row:
            d = dict(prof_row) if not isinstance(prof_row, dict) else prof_row
            profiles = int(d.get('c') or d.get('COUNT(*)') or 0)

    return {'storybooks': storybooks, 'child_profiles': profiles, 'month': month}


def increment_usage(user_id: int, resource: str) -> None:
    """Increment the monthly usage counter for storybooks.

    Child profile counts are derived from the children table, so
    no counter is incremented for that resource.
    """
    if resource != 'storybook':
        return

    month = _current_month()
    with get_db() as conn:
        # Atomic upsert — concurrent calls can't lose increments. Requires a
        # UNIQUE(user_id, month) constraint on usage_counters (already in schema).
        _execute(
            conn,
            "INSERT INTO usage_counters (user_id, month, storybooks_generated) "
            "VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, month) DO UPDATE SET "
            "storybooks_generated = storybooks_generated + 1, "
            "updated_at = datetime('now')",
            (user_id, month),
        )


def decrement_usage(user_id: int, resource: str) -> None:
    """Release a previously reserved storybook slot (e.g. when generation
    failed after the up-front reservation). Never drops below zero.

    Child profile counts are derived from the children table, so there is
    nothing to decrement for that resource.
    """
    if resource != 'storybook':
        return

    month = _current_month()
    with get_db() as conn:
        _execute(
            conn,
            "UPDATE usage_counters "
            "SET storybooks_generated = MAX(storybooks_generated - 1, 0), "
            "updated_at = datetime('now') "
            "WHERE user_id = ? AND month = ?",
            (user_id, month),
        )


def check_limit(user_id: int, resource: str) -> Tuple[bool, str]:
    """Return (allowed, reason). Reason is empty when allowed.

    resource: 'storybook' | 'child_profile'
    """
    tier = get_user_tier(user_id)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS[TIER_FREE])

    if resource == 'storybook':
        cap = limits['storybooks']
        if cap is None:
            return True, ''
        used = get_usage(user_id)['storybooks']
        if used >= cap:
            return False, (
                f'Monthly storybook limit reached ({cap} on {tier} tier). '
                'Upgrade to generate more.'
            )
        return True, ''

    if resource == 'child_profile':
        cap = limits['child_profiles']
        if cap is None:
            return True, ''
        used = get_usage(user_id)['child_profiles']
        if used >= cap:
            return False, (
                f'Child profile limit reached ({cap} on {tier} tier). '
                'Upgrade to add more heroes.'
            )
        return True, ''

    return True, ''


def set_user_tier(user_id: int, tier: str, expires_at: Optional[str] = None,
                  razorpay_subscription_id: Optional[str] = None) -> None:
    """Update a user's subscription tier and expiry. Used by billing flow."""
    if tier not in VALID_TIERS:
        raise ValueError(f'Invalid tier: {tier}')
    with get_db() as conn:
        _execute(
            conn,
            'UPDATE users SET subscription_tier = ?, subscription_status = ?, '
            'subscription_expires_at = ?, razorpay_subscription_id = COALESCE(?, razorpay_subscription_id) '
            'WHERE id = ?',
            (tier, 'active', expires_at, razorpay_subscription_id, user_id),
        )


def get_subscription_status(user_id: int) -> dict:
    """Aggregate tier + usage + limits for the /billing/status endpoint."""
    tier = get_user_tier(user_id)
    usage = get_usage(user_id)
    limits = TIER_LIMITS[tier]
    with get_db() as conn:
        row = _fetchone(
            conn,
            'SELECT subscription_status, subscription_expires_at FROM users WHERE id = ?',
            (user_id,),
        )
    d = (dict(row) if row and not isinstance(row, dict) else (row or {})) or {}
    return {
        'tier': tier,
        'status': d.get('subscription_status') or 'active',
        'expires_at': d.get('subscription_expires_at'),
        'usage': {
            'storybooks':     usage['storybooks'],
            'child_profiles': usage['child_profiles'],
            'month':          usage['month'],
        },
        'limits': {
            'storybooks':     limits['storybooks'],
            'child_profiles': limits['child_profiles'],
        },
        'features': dict(TIER_FEATURES[tier]),
    }
