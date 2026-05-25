"""
Moonface — camera-based hero character analysis.
Sends a JPEG snapshot to Azure OpenAI GPT-4o vision and returns
skin_tone / hair_style / hair_color for the character builder.
"""

import os
import base64
import json
import logging

import requests
from flask import Blueprint, request, jsonify

from auth import login_required
from subscription_decorators import require_feature

logger = logging.getLogger('brave_story.routes.moonface')

moonface_bp = Blueprint('moonface', __name__)

_VALID_SKIN_TONES  = {'light', 'medium-light', 'medium', 'medium-brown', 'brown', 'dark-brown'}
_VALID_HAIR_STYLES = {
    'short straight', 'short curly', 'long straight', 'long curly',
    'wavy', 'braids', 'pigtails', 'ponytail', 'high bun', 'afro', 'mohawk', 'buzz cut',
}
_VALID_HAIR_COLORS = {'black', 'brown', 'blonde', 'red', 'auburn', 'white'}

_SYSTEM = (
    "You analyse photos of children's faces to generate cartoon character descriptions. "
    "Respond with ONLY a JSON object — no markdown, no explanation."
)
_USER_TEXT = (
    "Look at the face in this image and return a JSON object with exactly these keys:\n"
    '  "skin_tone":  one of "light", "medium-light", "medium", "medium-brown", "brown", "dark-brown"\n'
    '  "hair_style": one of "short straight", "short curly", "long straight", "long curly", '
    '"wavy", "braids", "pigtails", "ponytail", "high bun", "afro", "mohawk", "buzz cut"\n'
    '  "hair_color": one of "black", "brown", "blonde", "red", "auburn", "white"\n'
    "Choose the value that best matches what you see. "
    "If a feature cannot be determined, pick the closest reasonable default."
)


def _coerce(value, valid_set, default):
    return value if value in valid_set else default


@moonface_bp.route('/api/moonface/analyze', methods=['POST'])
@login_required
@require_feature('face_api')
def analyze_face():
    data = request.get_json(silent=True) or {}
    image_data = data.get('image', '')

    if not image_data:
        return jsonify({'message': 'No image provided'}), 400

    # Strip data-URL prefix (data:image/jpeg;base64,...)
    if ',' in image_data:
        image_data = image_data.split(',', 1)[1]

    # Validate it's decodable base64
    try:
        base64.b64decode(image_data, validate=True)
    except Exception:
        return jsonify({'message': 'Invalid image encoding'}), 400

    api_key  = os.environ.get('GPT4O_VISION_API_KEY', '')
    endpoint = os.environ.get('GPT4O_VISION_ENDPOINT', '')
    if not api_key or not endpoint:
        return jsonify({'message': 'GPT-4o vision not configured'}), 500

    payload = {
        'messages': [
            {'role': 'system', 'content': _SYSTEM},
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': _USER_TEXT},
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': f'data:image/jpeg;base64,{image_data}',
                            'detail': 'low',
                        },
                    },
                ],
            },
        ],
        'max_tokens': 120,
        'temperature': 0,
    }

    try:
        resp = requests.post(
            endpoint,
            headers={'api-key': api_key, 'Content-Type': 'application/json'},
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()

        text = resp.json()['choices'][0]['message']['content'].strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()

        parsed = json.loads(text)

        return jsonify({
            'skin_tone':  _coerce(parsed.get('skin_tone'),  _VALID_SKIN_TONES,  'medium'),
            'hair_style': _coerce(parsed.get('hair_style'), _VALID_HAIR_STYLES, 'short straight'),
            'hair_color': _coerce(parsed.get('hair_color'), _VALID_HAIR_COLORS, 'brown'),
        })

    except requests.HTTPError as exc:
        logger.error('GPT-4o vision HTTP error: %s — %s', exc.response.status_code, exc.response.text[:300])
        return jsonify({'message': 'Vision API error — please try again'}), 502
    except Exception as exc:
        logger.error('Moonface analysis failed: %s', exc)
        return jsonify({'message': 'Analysis failed — please try again'}), 500
