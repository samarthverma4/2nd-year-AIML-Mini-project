"""
Subscription Routes Blueprint
─────────────────────────────
Read-only endpoints for the user's subscription tier and usage.
Billing endpoints (Razorpay) live in routes/billing.py (phase 2).
"""

import os
import logging
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request, g

import database_v2 as db
from auth import login_required
from subscription_service import (
    get_subscription_status, set_user_tier,
    TIER_LIMITS, TIER_FEATURES, TIER_PRICING_PAISE, VALID_TIERS,
)

logger = logging.getLogger('brave_story.routes.subscription')

subscription_bp = Blueprint('subscription', __name__)


@subscription_bp.route('/api/subscription/status', methods=['GET'])
@login_required
def status():
    """Return the current user's tier, usage counters, limits, and feature flags."""
    return jsonify(get_subscription_status(g.user_id))


@subscription_bp.route('/api/subscription/plans', methods=['GET'])
def plans():
    """Public plan catalogue for the pricing page."""
    return jsonify({
        'plans': [
            {
                'tier':       tier,
                'price_paise': TIER_PRICING_PAISE[tier],
                'limits':     TIER_LIMITS[tier],
                'features':   TIER_FEATURES[tier],
            }
            for tier in ('free', 'caregiver', 'hospital')
        ],
    })


# ── Admin: manually set a user's tier (used until Razorpay is wired up) ──

@subscription_bp.route('/api/admin/set-tier', methods=['POST'])
def admin_set_tier():
    """Set a user's subscription tier. Protected by ADMIN_SECRET header.

    Request:  X-Admin-Secret header + JSON {email, tier, days?}
    """
    expected = os.environ.get('ADMIN_SECRET', '')
    provided = request.headers.get('X-Admin-Secret', '')
    if not expected or provided != expected:
        return jsonify({'message': 'Forbidden'}), 403

    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    tier = (data.get('tier') or '').strip()
    days = int(data.get('days') or 30)

    if not email:
        return jsonify({'message': 'email is required'}), 400
    if tier not in VALID_TIERS:
        return jsonify({'message': f'tier must be one of {list(VALID_TIERS)}'}), 400

    user = db.get_user_by_email(email)
    if not user:
        return jsonify({'message': 'User not found'}), 404

    expires_at = None
    if tier != 'free':
        expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    set_user_tier(user['id'], tier, expires_at=expires_at)
    logger.info('Admin set tier user=%s tier=%s expires=%s', email, tier, expires_at)
    return jsonify({
        'success': True,
        'user_id': user['id'],
        'email': email,
        'tier': tier,
        'expires_at': expires_at,
    })
