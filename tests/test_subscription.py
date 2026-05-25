"""
Tests for the subscription tier system: limits, feature gating,
usage counters, and tier expiry.
"""

import pytest

import database_v2 as db
import subscription_service as subs


def _make_child(client, auth_header, name='Hero'):
    return client.post('/api/children', json={
        'name': name, 'age': 6, 'gender': 'neutral',
    }, headers=auth_header)


def _user_id_from_header(client, auth_header):
    r = client.get('/api/auth/me', headers=auth_header)
    return r.get_json()['id']


# ── Status endpoint ─────────────────────────────────────────────────

def test_new_user_defaults_to_free_tier(client, auth_header):
    r = client.get('/api/subscription/status', headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert body['tier'] == 'free'
    assert body['limits']['storybooks'] == 3
    assert body['limits']['child_profiles'] == 1
    assert body['features']['multilingual_tts'] is False
    assert body['features']['face_api'] is False


def test_plans_endpoint_public(client):
    r = client.get('/api/subscription/plans')
    assert r.status_code == 200
    plans = r.get_json()['plans']
    assert {p['tier'] for p in plans} == {'free', 'caregiver', 'hospital'}


# ── Tier helpers ────────────────────────────────────────────────────

def test_get_user_tier_unknown_user_is_free():
    assert subs.get_user_tier(99999) == 'free'


def test_set_and_read_tier(client, auth_header):
    uid = _user_id_from_header(client, auth_header)
    subs.set_user_tier(uid, 'caregiver', expires_at='2099-01-01T00:00:00+00:00')
    assert subs.get_user_tier(uid) == 'caregiver'


def test_expired_subscription_falls_back_to_free(client, auth_header):
    uid = _user_id_from_header(client, auth_header)
    subs.set_user_tier(uid, 'caregiver', expires_at='2000-01-01T00:00:00+00:00')
    assert subs.get_user_tier(uid) == 'free'


# ── Feature gating ──────────────────────────────────────────────────

def test_free_user_blocked_from_translate(client, auth_header):
    r = client.post('/api/translate', json={
        'texts': ['hello'], 'target_lang': 'hi',
    }, headers=auth_header)
    assert r.status_code == 403
    assert r.get_json().get('upgrade_required') is True


def test_free_user_blocked_from_moonface(client, auth_header):
    r = client.post('/api/moonface/analyze', json={'image': 'x'}, headers=auth_header)
    assert r.status_code == 403


def test_caregiver_passes_translate_feature_check(client, auth_header, monkeypatch):
    uid = _user_id_from_header(client, auth_header)
    subs.set_user_tier(uid, 'caregiver', expires_at='2099-01-01T00:00:00+00:00')

    # Translator may not be configured in tests — we only care that the
    # decorator doesn't return 403. 503 (not configured) is the expected path.
    r = client.post('/api/translate', json={
        'texts': ['hello'], 'target_lang': 'hi',
    }, headers=auth_header)
    assert r.status_code != 403


# ── Child profile limit ─────────────────────────────────────────────

def test_free_user_blocked_after_first_child_profile(client, auth_header):
    r1 = _make_child(client, auth_header, 'Aria')
    assert r1.status_code == 201

    r2 = _make_child(client, auth_header, 'Bran')
    assert r2.status_code == 429
    assert r2.get_json().get('upgrade_required') is True


def test_caregiver_can_create_three_child_profiles(client, auth_header):
    uid = _user_id_from_header(client, auth_header)
    subs.set_user_tier(uid, 'caregiver', expires_at='2099-01-01T00:00:00+00:00')
    for n in ('Aria', 'Bran', 'Cleo'):
        assert _make_child(client, auth_header, n).status_code == 201
    # 4th should fail
    assert _make_child(client, auth_header, 'Dax').status_code == 429


# ── Usage counter ───────────────────────────────────────────────────

def test_increment_usage_persists_per_month(client, auth_header):
    uid = _user_id_from_header(client, auth_header)
    assert subs.get_usage(uid)['storybooks'] == 0
    subs.increment_usage(uid, 'storybook')
    subs.increment_usage(uid, 'storybook')
    assert subs.get_usage(uid)['storybooks'] == 2


def test_check_limit_blocks_after_cap(client, auth_header):
    uid = _user_id_from_header(client, auth_header)
    for _ in range(3):
        subs.increment_usage(uid, 'storybook')
    allowed, reason = subs.check_limit(uid, 'storybook')
    assert allowed is False
    assert 'limit' in reason.lower()


def test_admin_set_tier_requires_secret(client, auth_header, monkeypatch):
    monkeypatch.setenv('ADMIN_SECRET', 'sup3r-secret')
    r = client.post('/api/admin/set-tier',
                    json={'email': 'test@example.com', 'tier': 'caregiver'})
    assert r.status_code == 403


def test_admin_set_tier_with_secret_upgrades_user(client, auth_header, monkeypatch):
    monkeypatch.setenv('ADMIN_SECRET', 'sup3r-secret')
    r = client.post('/api/admin/set-tier',
                    json={'email': 'test@example.com', 'tier': 'caregiver', 'days': 30},
                    headers={'X-Admin-Secret': 'sup3r-secret'})
    assert r.status_code == 200
    assert r.get_json()['tier'] == 'caregiver'

    # follow up: status reflects new tier
    s = client.get('/api/subscription/status', headers=auth_header).get_json()
    assert s['tier'] == 'caregiver'


def test_analytics_blocked_for_free_tier(client, auth_header):
    r = client.get('/api/analytics/engagement', headers=auth_header)
    assert r.status_code == 403


def test_analytics_allowed_for_hospital_tier(client, auth_header):
    uid = _user_id_from_header(client, auth_header)
    subs.set_user_tier(uid, 'hospital')
    r = client.get('/api/analytics/engagement', headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert 'per_child' in body
    assert 'per_day' in body


def test_pdf_export_blocked_for_free_tier(client, auth_header):
    # Need a story to attempt export — use direct DB insert to avoid AI calls
    story = db.create_story(
        child_name='Aria', age=6, gender='neutral', condition='', hero_characteristics='',
        story_title='Test', pages=[{'text': 'hi', 'imageUrl': None, 'pageNumber': 1}],
        user_id=_user_id_from_header(client, auth_header),
    )
    assert story is not None
    r = client.get('/api/stories/{}/pdf'.format(story['id']), headers=auth_header)
    assert r.status_code == 403


def test_pdf_export_works_for_caregiver(client, auth_header):
    uid = _user_id_from_header(client, auth_header)
    subs.set_user_tier(uid, 'caregiver', expires_at='2099-01-01T00:00:00+00:00')
    story = db.create_story(
        child_name='Aria', age=6, gender='neutral', condition='', hero_characteristics='',
        story_title='Test Story', pages=[{'text': 'A brave hero.', 'imageUrl': None, 'pageNumber': 1}],
        user_id=uid,
    )
    assert story is not None
    r = client.get('/api/stories/{}/pdf'.format(story['id']), headers=auth_header)
    # 200 = pdf produced; 503 = reportlab not installed (acceptable in dev envs)
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        assert r.content_type == 'application/pdf'
        assert r.data[:4] == b'%PDF'


def test_hospital_tier_unlimited_storybooks(client, auth_header):
    uid = _user_id_from_header(client, auth_header)
    subs.set_user_tier(uid, 'hospital')
    for _ in range(50):
        subs.increment_usage(uid, 'storybook')
    allowed, _ = subs.check_limit(uid, 'storybook')
    assert allowed is True
