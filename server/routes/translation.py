"""
Translation Blueprint
─────────────────────
Azure AI Translator endpoints.

Endpoints:
  GET  /api/translate/config  — available flag + supported-language catalogue (public)
  POST /api/translate         — translate one or more strings (JWT required)

Request body (POST):
  {
    "texts":        ["string", ...]   (or "text": "single string"),
    "target_lang":  "hi",
    "story_id":     123  (optional — enables automatic name protection)
  }

Response:
  {
    "translated":  ["…", …],
    "target_lang": "hi",
    "direction":   "ltr" | "rtl"
  }
"""

import logging
from flask import Blueprint, request, jsonify, g

from auth import login_required
from subscription_decorators import require_feature
from translator import (
    translate_batch, is_available, is_rtl, normalise_lang,
    LANGUAGES, LANG_CODES,
)
import database_v2 as db

logger = logging.getLogger('brave_story.routes.translation')

translation_bp = Blueprint('translation', __name__)

# Hard cap per request to contain abuse and keep well under Azure's limits.
_MAX_ITEMS       = 50
_MAX_TOTAL_CHARS = 20000


@translation_bp.route('/api/translate/config', methods=['GET'])
def translate_config():
    """Return whether Azure Translator is available and the language catalogue."""
    return jsonify({
        'available': is_available(),
        'languages': LANGUAGES if is_available() else [],
    })


@translation_bp.route('/api/translate', methods=['POST'])
@login_required
@require_feature('multilingual_tts')
def translate_endpoint():
    if not is_available():
        return jsonify({'message': 'Translation not available — Azure Translator not configured'}), 503

    data = request.get_json(silent=True) or {}

    texts = data.get('texts')
    if texts is None:
        single = data.get('text')
        texts  = [single] if isinstance(single, str) and single.strip() else []
    if not isinstance(texts, list) or not texts:
        return jsonify({'message': 'texts is required (non-empty list of strings)'}), 400
    if len(texts) > _MAX_ITEMS:
        return jsonify({'message': f'too many items (max {_MAX_ITEMS})'}), 413
    if any(not isinstance(t, str) for t in texts):
        return jsonify({'message': 'all items in texts must be strings'}), 400
    if sum(len(t) for t in texts) > _MAX_TOTAL_CHARS:
        return jsonify({'message': 'payload too large'}), 413

    target_lang = normalise_lang(data.get('target_lang', ''))
    if target_lang not in LANG_CODES:
        return jsonify({'message': f'unsupported target_lang: {data.get("target_lang")}'}), 400

    # Collect protected terms. Frontend can pass them explicitly; if a
    # story_id is supplied we also protect the hero's name automatically.
    protected = list(data.get('protected_terms') or [])
    story_id  = data.get('story_id')
    if story_id:
        try:
            story = db.get_story(int(story_id), user_id=g.user_id)
            if story:
                name = (story.get('childName') or '').strip()
                if name:
                    protected.append(name)
        except (ValueError, TypeError):
            pass  # invalid story_id — ignore, carry on without auto-protection
        except Exception as exc:
            logger.warning('Could not resolve story_id=%s for protection: %s', story_id, exc)

    try:
        translated = translate_batch(texts, target_lang, 'en', protected)
    except ValueError as exc:
        return jsonify({'message': str(exc)}), 400
    except Exception as exc:
        logger.error('Translation failed: %s', exc)
        return jsonify({'message': 'Translation failed — try again'}), 500

    return jsonify({
        'translated':  translated,
        'target_lang': target_lang,
        'direction':   'rtl' if is_rtl(target_lang) else 'ltr',
    })
