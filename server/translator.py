"""
Translation via Azure OpenAI (gpt-realtime-translate)
─────────────────────────────────────────────────────
Wraps an Azure OpenAI chat-completion deployment to translate a list of
strings into a target language. Proper nouns (e.g. the hero's name) can
be passed via ``protected_terms`` and are preserved verbatim through a
system-prompt instruction.

Required env vars:
  AZURE_OPENAI_TRANSLATE_API_KEY   — subscription key
  AZURE_OPENAI_TRANSLATE_ENDPOINT  — full chat-completions URL incl. api-version
  AZURE_OPENAI_TRANSLATE_MODEL     — deployment / model id (default: gpt-realtime-translate)
"""

import os
import json
import logging
from typing import List, Optional
import requests

logger = logging.getLogger('brave_story.translator')

# Languages surfaced to the frontend. ISO 639-1 codes.
LANGUAGES = [
    {'code': 'en', 'name': 'English',   'rtl': False},
    {'code': 'hi', 'name': 'Hindi',     'rtl': False},
    {'code': 'bn', 'name': 'Bengali',   'rtl': False},
    {'code': 'ta', 'name': 'Tamil',     'rtl': False},
    {'code': 'te', 'name': 'Telugu',    'rtl': False},
    {'code': 'mr', 'name': 'Marathi',   'rtl': False},
    {'code': 'gu', 'name': 'Gujarati',  'rtl': False},
    {'code': 'kn', 'name': 'Kannada',   'rtl': False},
    {'code': 'ml', 'name': 'Malayalam', 'rtl': False},
    {'code': 'pa', 'name': 'Punjabi',   'rtl': False},
    {'code': 'ur', 'name': 'Urdu',      'rtl': True},
    {'code': 'or', 'name': 'Odia',      'rtl': False},
    {'code': 'as', 'name': 'Assamese',  'rtl': False},
    {'code': 'sa', 'name': 'Sanskrit',  'rtl': False},
    {'code': 'es', 'name': 'Spanish',   'rtl': False},
    {'code': 'fr', 'name': 'French',    'rtl': False},
    {'code': 'de', 'name': 'German',    'rtl': False},
    {'code': 'zh-Hans', 'name': 'Chinese (Simplified)', 'rtl': False},
    {'code': 'ja', 'name': 'Japanese',  'rtl': False},
    {'code': 'ar', 'name': 'Arabic',    'rtl': True},
]

LANG_CODES = {L['code'] for L in LANGUAGES}
RTL_LANGS  = {L['code'] for L in LANGUAGES if L['rtl']}
LANG_NAMES = {L['code']: L['name'] for L in LANGUAGES}

# Frontend historically uses ISO-639-1 "zh" — accept that alias.
LANG_ALIASES = {'zh': 'zh-Hans'}


def _key() -> str:
    return os.environ.get('AZURE_OPENAI_TRANSLATE_API_KEY', '')


def _endpoint() -> str:
    return os.environ.get('AZURE_OPENAI_TRANSLATE_ENDPOINT', '').strip()


def _model() -> str:
    return os.environ.get('AZURE_OPENAI_TRANSLATE_MODEL', 'gpt-realtime-translate')


def is_available() -> bool:
    return bool(_key() and _endpoint())


def normalise_lang(code: str) -> str:
    code = (code or '').strip()
    return LANG_ALIASES.get(code, code)


def _build_system_prompt(target_name: str, protected_terms: List[str]) -> str:
    base = (
        f"You are a precise translator. Translate every input string into {target_name}. "
        "Respond with ONLY a JSON object of the form "
        '{"translations": ["...", "...", ...]} — same length, same order as inputs. '
        "Preserve line breaks. Do not add commentary or explanation. "
        "Do not translate inside HTML tags."
    )
    terms = [t for t in (protected_terms or []) if t and isinstance(t, str)]
    if terms:
        joined = ', '.join(f'"{t}"' for t in terms)
        base += (
            f" Keep the following proper nouns verbatim — do not translate or transliterate "
            f"them: {joined}."
        )
    return base


def translate_batch(
    texts: List[str],
    target_lang: str,
    source_lang: str = 'en',
    protected_terms: Optional[List[str]] = None,
) -> List[str]:
    """Translate a list of strings. Output order matches input order."""
    if not is_available():
        raise RuntimeError(
            'Translator not configured — set AZURE_OPENAI_TRANSLATE_API_KEY '
            'and AZURE_OPENAI_TRANSLATE_ENDPOINT'
        )

    target_lang = normalise_lang(target_lang).strip()
    if target_lang not in LANG_CODES:
        raise ValueError(f'unsupported target language: {target_lang}')

    if source_lang == target_lang:
        return list(texts)

    target_name = LANG_NAMES.get(target_lang, target_lang)
    system_prompt = _build_system_prompt(target_name, protected_terms or [])
    user_payload = json.dumps({'inputs': list(texts)}, ensure_ascii=False)

    payload = {
        'model': _model(),
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user',   'content': user_payload},
        ],
        'max_tokens': 4096,
    }
    headers = {
        'api-key':       _key(),
        'Content-Type':  'application/json',
    }

    try:
        resp = requests.post(_endpoint(), headers=headers, json=payload, timeout=60)
    except requests.RequestException as exc:
        logger.error('Translator network error: %s', exc)
        raise

    if not resp.ok:
        logger.error('Translator %s: %s', resp.status_code, resp.text[:500])
        resp.raise_for_status()

    try:
        body = resp.json()
        # Azure OpenAI Chat Completions: choices[0].message.content
        content = ''
        choices = body.get('choices') or []
        if choices:
            message = choices[0].get('message') or {}
            msg_content = message.get('content')
            if isinstance(msg_content, str):
                content = msg_content.strip()
            elif isinstance(msg_content, list):
                # Some deployments return content as a list of parts.
                parts = []
                for block in msg_content:
                    txt = block.get('text') if isinstance(block, dict) else None
                    if isinstance(txt, str):
                        parts.append(txt)
                content = ''.join(parts).strip()

        # Strip markdown code fences if model wrapped JSON.
        if content.startswith('```json'):
            content = content[7:]
        elif content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()

        parsed = json.loads(content)
        translations = parsed.get('translations') or []
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.error('Translator response parse error: %s — body=%s', exc, resp.text[:500])
        raise RuntimeError('Translator returned an unparseable response')

    # Fall back to original where the model dropped an entry.
    out = []
    for i, original in enumerate(texts):
        t = translations[i] if i < len(translations) else ''
        if not isinstance(t, str) or not t.strip():
            out.append(original)
        else:
            out.append(t)
    return out


def translate(
    text: str,
    target_lang: str,
    source_lang: str = 'en',
    protected_terms: Optional[List[str]] = None,
) -> str:
    """Single-string convenience wrapper over ``translate_batch``."""
    return translate_batch([text], target_lang, source_lang, protected_terms)[0]


def is_rtl(target_lang: str) -> bool:
    return normalise_lang(target_lang) in RTL_LANGS
