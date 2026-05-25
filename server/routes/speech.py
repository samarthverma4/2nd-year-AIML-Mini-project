"""
Speech Blueprint
────────────────
Azure OpenAI TTS endpoints.

Endpoints:
  GET  /api/tts/config  — availability flag + voice catalogue (public)
  POST /api/tts         — synthesise text → MP3 (JWT required)
"""

import logging
from flask import Blueprint, request, jsonify, Response

from auth import login_required
from tts_engine import synthesize, is_available, VOICES, DEFAULT_VOICE

logger = logging.getLogger('brave_story.routes.speech')

speech_bp = Blueprint('speech', __name__)


@speech_bp.route('/api/tts/config', methods=['GET'])
def tts_config():
    """Return whether Azure TTS is available and the voice catalogue."""
    available = is_available()
    return jsonify({'available': available, 'voices': VOICES if available else []})


@speech_bp.route('/api/tts', methods=['POST'])
@login_required
def text_to_speech():
    """Synthesise text to MP3 audio via Azure OpenAI TTS.

    Request JSON: ``{ "text": "...", "voice": "nova", "speed": 1.0 }``
    Returns ``audio/mpeg`` stream.
    """
    if not is_available():
        return jsonify({'message': 'TTS not available — Azure TTS not configured'}), 503

    data  = request.get_json() or {}
    text  = (data.get('text') or '').strip()
    voice = (data.get('voice') or DEFAULT_VOICE).strip()
    try:
        speed = float(data.get('speed', 1.0))
    except (TypeError, ValueError):
        return jsonify({'message': 'speed must be a number'}), 400
    # Clamp to Azure's accepted range
    speed = max(0.25, min(4.0, speed))

    if not text:
        return jsonify({'message': 'text is required'}), 400

    if len(text) > 4096:
        text = text[:4096]

    try:
        mp3_bytes = synthesize(text, voice=voice, speed=speed)
        return Response(
            mp3_bytes,
            content_type='audio/mpeg',
            headers={'Cache-Control': 'no-store'},
        )
    except Exception as exc:
        logger.error('TTS synthesis error: %s', exc)
        return jsonify({'message': 'TTS generation failed'}), 500
