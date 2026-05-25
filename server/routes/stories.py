"""
Story & Children Routes Blueprint
──────────────────────────────────
CRUD for stories and children profiles, story generation,
feedback, and personalization.
"""

import os
import json
import time
import logging
import base64
import re
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor


# Words that frequently trigger Azure image content moderation. We strip
# these from a prompt before retrying when the first call gets a
# `moderation_blocked` response.
_MODERATION_TRIGGER_WORDS = re.compile(
    r'\b(needle|needles|syringe|syringes|blood|wound|wounds|gore|gory|injection|'
    r'injections|scary|frightening|terrified|terror|hospital|clinical|cold medical|'
    r'sick|illness|disease|patient|dying|death|hurt|pain|painful|scar|scars|surgery)\b',
    re.IGNORECASE,
)


def _sanitize_for_moderation_retry(prompt: str) -> str:
    """Remove tokens known to upset Azure's image content filter, for a one-shot retry."""
    cleaned = _MODERATION_TRIGGER_WORDS.sub('', prompt)
    # Collapse any whitespace gaps the substitution left behind.
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    return cleaned

from flask import Blueprint, request, jsonify, g, Response

import database_v2 as db
from auth import login_required
from subscription_decorators import check_usage_limit, require_feature
from subscription_service import increment_usage, decrement_usage
from content_safety import validate_input, moderate_output, moderate_image_prompt, sanitize_html
from monitoring import usage_counter, AIGenerationTracker, perf_tracker
from prompt_manager import build_story_prompt, build_image_prompt, build_character_description

logger = logging.getLogger('brave_story.routes.stories')

stories_bp = Blueprint('stories', __name__)

# cloud storage injected at registration time
_image_storage = None


def init_stories_bp(image_storage, limiter=None):
    """Inject the image storage backend and rate limiter into the blueprint."""
    global _image_storage
    _image_storage = image_storage
    if limiter:
        limiter.limit("5 per minute")(generate_story)


def _refresh_image_urls(story):
    """Regenerate S3 presigned URLs for story page images.

    Stored presigned URLs expire after 7 days. This extracts the S3 key
    from stale URLs and generates fresh presigned URLs on every read.
    """
    if not _image_storage or not story:
        return story

    from cloud_storage import S3Storage
    if not isinstance(_image_storage, S3Storage):
        return story

    pages = story.get('pages')
    if isinstance(pages, str):
        try:
            pages = json.loads(pages)
        except (json.JSONDecodeError, TypeError):
            return story
    if not pages:
        return story

    changed = False
    for page in pages:
        url = page.get('imageUrl')
        if not url:
            continue
        # Extract the filename from the presigned URL
        filename = _extract_s3_filename(url)
        if filename:
            page['imageUrl'] = _image_storage.get_url(filename)
            changed = True

    if changed:
        story['pages'] = pages
    return story


def _extract_s3_filename(url):
    """Extract the image filename from a presigned S3 URL or local path."""
    if not url:
        return None
    # Full S3 presigned URL: https://bucket.s3.amazonaws.com/generated_images/file.png?...
    if 's3.amazonaws.com' in url or 's3.' in url:
        parsed = urlparse(url)
        path = parsed.path.lstrip('/')
        # Key is like "generated_images/story_123_1.png" → extract filename
        if 'generated_images/' in path:
            return path.split('generated_images/')[-1]
        return path
    # Local URL: /generated_images/file.png
    if url.startswith('/generated_images/'):
        return url.split('/generated_images/')[-1].split('?')[0]
    return None


# ── Children Profile Routes ──────────────────────────────────────────

@stories_bp.route('/api/children', methods=['GET'])
@login_required
def list_children():
    """List all children profiles belonging to the authenticated user."""
    return jsonify(db.get_children(g.user_id))


@stories_bp.route('/api/children', methods=['POST'])
@login_required
@check_usage_limit('child_profile')
def add_child():
    """Create a new child profile.

    Expects JSON with ``name``, ``age``, and optionally ``gender``
    and ``conditions``.  Validates inputs server-side before saving.
    """
    data = request.get_json()

    # ── Server-side input validation ─────────────────────────────
    name = (data.get('name') or '').strip()
    age = data.get('age')
    gender = (data.get('gender') or 'neutral').strip()
    conditions = data.get('conditions', [])
    medical_challenge = (data.get('medicalChallenge') or '').strip()
    characteristics = (data.get('characteristics') or '').strip()
    hero_character = data.get('heroCharacter')  # dict or None

    if not name or len(name) < 1 or len(name) > 50:
        return jsonify({'message': 'Child name must be 1-50 characters'}), 400
    if not isinstance(age, int) or age < 2 or age > 18:
        return jsonify({'message': 'Age must be an integer between 2 and 18'}), 400
    if gender not in ('male', 'female', 'neutral'):
        return jsonify({'message': 'Gender must be male, female, or neutral'}), 400
    if not isinstance(conditions, list) or len(conditions) > 10:
        return jsonify({'message': 'Conditions must be a list (max 10 items)'}), 400
    for c in conditions:
        if not isinstance(c, str) or len(c) > 200:
            return jsonify({'message': 'Each condition must be a string (max 200 chars)'}), 400
    if len(medical_challenge) > 300:
        return jsonify({'message': 'Medical challenge must be under 300 characters'}), 400
    if len(characteristics) > 500:
        return jsonify({'message': 'Characteristics must be under 500 characters'}), 400
    if hero_character is not None and not isinstance(hero_character, dict):
        return jsonify({'message': 'heroCharacter must be an object'}), 400

    # Sanitize text inputs before storage (XSS prevention)
    name = sanitize_html(name)
    conditions = [sanitize_html(c) for c in conditions]
    medical_challenge = sanitize_html(medical_challenge)
    characteristics = sanitize_html(characteristics)

    child = db.create_child(g.user_id, name, age, gender, conditions,
                            medical_challenge=medical_challenge,
                            characteristics=characteristics,
                            hero_character=hero_character)
    return jsonify(child), 201


@stories_bp.route('/api/children/<int:child_id>', methods=['PUT'])
@login_required
def update_child(child_id):
    """Update an existing child profile by ID (only if owned by authenticated user)."""
    data = request.get_json()

    # Sanitize text fields before passing to DB (XSS prevention)
    if 'name' in data and isinstance(data['name'], str):
        data['name'] = sanitize_html(data['name'].strip())
    if 'conditions' in data and isinstance(data['conditions'], list):
        data['conditions'] = [sanitize_html(c) for c in data['conditions'] if isinstance(c, str)]
    if 'medicalChallenge' in data and isinstance(data['medicalChallenge'], str):
        data['medical_challenge'] = sanitize_html(data.pop('medicalChallenge').strip())
    elif 'medicalChallenge' in data:
        data.pop('medicalChallenge')
    if 'characteristics' in data and isinstance(data['characteristics'], str):
        data['characteristics'] = sanitize_html(data['characteristics'].strip())
    if 'heroCharacter' in data:
        data['hero_character'] = data.pop('heroCharacter')  # rename to DB column

    child = db.update_child(child_id, user_id=g.user_id, **data)
    if not child:
        return jsonify({'message': 'Child not found'}), 404
    return jsonify(child)


@stories_bp.route('/api/children/<int:child_id>', methods=['DELETE'])
@login_required
def delete_child(child_id):
    """Delete a child profile by ID (only if owned by authenticated user)."""
    if not db.delete_child(child_id, user_id=g.user_id):
        return jsonify({'message': 'Child not found'}), 404
    return jsonify({'success': True})


# ── Story CRUD Routes ────────────────────────────────────────────────

@stories_bp.route('/api/stories', methods=['GET'])
@login_required
def list_stories():
    """Return stories belonging to the authenticated user."""
    stories = db.get_stories(user_id=g.user_id)
    return jsonify([_refresh_image_urls(s) for s in stories])


@stories_bp.route('/api/stories/favorites', methods=['GET'])
@login_required
def favorite_stories():
    """Return only favorite stories belonging to the authenticated user."""
    stories = db.get_favorite_stories(user_id=g.user_id)
    return jsonify([_refresh_image_urls(s) for s in stories])


@stories_bp.route('/api/stories/<int:story_id>', methods=['GET'])
@login_required
def get_story(story_id):
    """Retrieve a single story by ID (only if owned by authenticated user)."""
    story = db.get_story(story_id, user_id=g.user_id)
    if not story:
        return jsonify({'message': 'Story not found'}), 404
    return jsonify(_refresh_image_urls(story))


@stories_bp.route('/api/stories/<int:story_id>', methods=['DELETE'])
@login_required
def delete_story(story_id):
    """Delete a story by ID (only if owned by authenticated user)."""
    deleted = db.delete_story(story_id, user_id=g.user_id)
    if not deleted:
        return jsonify({'message': 'Story not found'}), 404
    return jsonify({'success': True, 'message': 'Story deleted successfully'})


@stories_bp.route('/api/stories/<int:story_id>/favorite', methods=['POST'])
@login_required
def toggle_favorite(story_id):
    """Toggle the favorite flag on a story (only if owned by authenticated user)."""
    story = db.toggle_favorite(story_id, user_id=g.user_id)
    if not story:
        return jsonify({'message': 'Story not found'}), 404
    return jsonify(story)


def _generate_image_azure_gpt(api_key, endpoint, prompt):
    """Generate an image via Azure OpenAI gpt-image-1.5 and return raw image bytes."""
    headers = {
        'api-key': api_key,
        'Content-Type': 'application/json',
    }
    payload = {
        'prompt': prompt,
        'n': 1,
        'size': '1536x1024',
    }
    print(f'[IMG] POST {endpoint[:80]}... size={payload["size"]}', flush=True)
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=180)
    print(f'[IMG] response status={resp.status_code}', flush=True)

    # Retry once with a sanitized prompt if Azure's content filter fired.
    if resp.status_code == 400 and 'moderation_blocked' in resp.text:
        print('[IMG] moderation_blocked — retrying with sanitized prompt', flush=True)
        payload['prompt'] = _sanitize_for_moderation_retry(prompt)
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=180)
        print(f'[IMG] retry status={resp.status_code}', flush=True)

    if not resp.ok:
        print(f'[IMG] error body: {resp.text[:800]}', flush=True)
        logger.error('gpt-image %s: %s', resp.status_code, resp.text[:500])
        resp.raise_for_status()
    data = resp.json()
    items = data.get('data') or []
    if not items:
        logger.error('gpt-image returned no data: %s', str(data)[:300])
        return None
    entry = items[0]
    b64 = entry.get('b64_json')
    if b64:
        return base64.b64decode(b64)
    # Some deployments return a URL instead — fetch it.
    url = entry.get('url')
    if url:
        img_resp = requests.get(url, timeout=60)
        img_resp.raise_for_status()
        return img_resp.content
    logger.error('gpt-image entry has neither b64_json nor url: %s', str(entry)[:300])
    return None


# ── Story Generation ─────────────────────────────────────────────────

@stories_bp.route('/api/stories/generate', methods=['POST'])
@login_required
@check_usage_limit('storybook')
def generate_story():
    """Generate a new story using Azure OpenAI GPT-5.5 + Azure gpt-image-1.5.

    Accepts JSON with ``childName``, ``age``, ``gender``, ``condition``,
    ``heroCharacteristics``, and optional ``childId``.  Validates all
    inputs server-side before AI generation.
    """
    start_time = time.time()
    user_id = g.user_id
    usage_reserved = False  # set True once a slot is reserved; released on failure

    try:
        data = request.get_json()
        child_id = data.get('childId')

        # If a hero profile is linked, auto-fill hero fields from it
        child_profile = None
        if child_id:
            if not db.verify_child_owner(child_id, user_id):
                return jsonify({'message': 'Child profile not found'}), 404
            child_profile = db.get_child(child_id, user_id=user_id)

        if child_profile:
            child_name = child_profile.get('name', '').strip()
            age = int(child_profile.get('age', 6))
            gender = child_profile.get('gender', 'neutral').strip()
            # Prefer rich text medical_challenge; fall back to conditions list
            mc = child_profile.get('medicalChallenge', '').strip()
            if not mc and child_profile.get('conditions'):
                mc = ', '.join(child_profile['conditions'])
            condition = mc or (data.get('condition') or '').strip()
            hero_characteristics = child_profile.get('characteristics', '').strip() or (data.get('heroCharacteristics') or '').strip()
            hero_character = child_profile.get('heroCharacter') or data.get('heroCharacter')
        else:
            child_name = (data.get('childName') or '').strip()
            age = int(data.get('age', 6))
            gender = (data.get('gender') or 'neutral').strip()
            condition = (data.get('condition') or '').strip()
            hero_characteristics = (data.get('heroCharacteristics') or '').strip()
            hero_character = data.get('heroCharacter')

        # Custom story settings
        story_length = (data.get('storyLength') or '').strip()
        tone = (data.get('tone') or '').strip()
        theme = (data.get('theme') or '').strip()
        villain_type = (data.get('villainType') or '').strip()
        ending_type = (data.get('endingType') or '').strip()
        illustration_style = (data.get('illustrationStyle') or '').strip()
        reading_level = (data.get('readingLevel') or '').strip()

        # Optional character builder data
        character_description = ''
        if hero_character and isinstance(hero_character, dict):
            character_description = build_character_description(hero_character)

        # 0. Content safety: validate & moderate input
        valid, error = validate_input(child_name, age, condition, hero_characteristics)
        if not valid:
            logger.warning(f'Input validation failed: {error}')
            return jsonify({'message': error}), 400

        # Reserve the usage slot up-front (before the long, expensive AI calls)
        # so concurrent requests can't all pass the @check_usage_limit gate and
        # exceed the cap.
        try:
            increment_usage(user_id, 'storybook')
            usage_reserved = True
        except Exception as e:
            logger.warning(f'Failed to reserve usage slot: {e}')

        # Load personalization data if a child profile is linked
        preferences = []
        story_history = []
        if child_id:
            try:
                preferences = db.get_preferences(child_id)
                story_history = db.get_child_story_history(child_id)
            except Exception as e:
                logger.warning(f'Failed to load personalization: {e}')

        # 1. Generate story text with Azure OpenAI Responses API (GPT-5.5)
        # Falls back to legacy CLAUDE_* env vars during migration.
        text_key = (os.environ.get('AZURE_OPENAI_TEXT_API_KEY')
                    or os.environ.get('CLAUDE_API_KEY') or '')
        text_endpoint = (os.environ.get('AZURE_OPENAI_TEXT_ENDPOINT')
                         or os.environ.get('CLAUDE_ENDPOINT') or '')
        text_model = os.environ.get('AZURE_OPENAI_TEXT_MODEL', 'gpt-5.5')
        if not text_key or not text_endpoint:
            return jsonify({'message': 'AZURE_OPENAI_TEXT_API_KEY / AZURE_OPENAI_TEXT_ENDPOINT not configured'}), 500

        prompt = build_story_prompt(
            child_name=child_name, age=age, gender=gender,
            condition=condition, hero_characteristics=hero_characteristics,
            preferences=preferences, story_history=story_history,
            story_length=story_length, tone=tone, theme=theme,
            villain_type=villain_type, ending_type=ending_type,
            illustration_style=illustration_style, reading_level=reading_level,
            character_description=character_description,
        )

        # 'claude' tracker tag kept for credit/monitoring continuity — it now
        # measures Azure OpenAI text generation regardless of underlying model.
        with AIGenerationTracker('claude', text_model):
            claude_start = time.time()
            resp = requests.post(
                text_endpoint,
                headers={'api-key': text_key, 'Content-Type': 'application/json'},
                json={
                    'model': text_model,
                    'input': prompt,
                    'max_output_tokens': 4096,
                },
                timeout=120,
            )
            resp.raise_for_status()
            result = resp.json()

            # Azure Responses API: prefer `output_text`, else walk `output[*].content[*].text`
            content = (result.get('output_text') or '').strip()
            if not content:
                parts = []
                for item in result.get('output', []) or []:
                    for block in item.get('content', []) or []:
                        txt = block.get('text')
                        if isinstance(txt, str):
                            parts.append(txt)
                        elif isinstance(txt, dict) and 'value' in txt:
                            parts.append(txt['value'])
                content = ''.join(parts).strip()

            if not content:
                # Empty response — log full shape so we can diagnose (refusal, filter, truncation, etc.)
                print(f'[TEXT] EMPTY response. status={resp.status_code} body={resp.text[:2000]}', flush=True)
                logger.error('GPT-5.5 returned empty content. Response: %s', resp.text[:1500])
                usage_counter.record('claude', success=False)
                return jsonify({'message': 'Story text generation returned empty — likely blocked by content filter. Try different inputs.'}), 502

            claude_ms = int((time.time() - claude_start) * 1000)
            usage_counter.record('claude', success=True)

        # Strip markdown code fences if present
        if content.startswith('```json'):
            content = content[7:]
        elif content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()

        try:
            story_data = json.loads(content)
        except json.JSONDecodeError:
            print(f'[TEXT] NON-JSON response (len={len(content)}). content[:500]={content[:500]!r}', flush=True)
            print(f'[TEXT] full raw response: {resp.text[:2000]}', flush=True)
            logger.error('GPT-5.5 returned non-JSON. content=%r raw=%s', content[:500], resp.text[:1500])
            usage_counter.record('claude', success=False)
            return jsonify({'message': 'Story text was not valid JSON — likely a content filter or refusal. Try different inputs.'}), 502

        # 1b. Content safety: moderate AI output
        all_moderation_flags = []
        for page in story_data.get('pages', []):
            cleaned_text, warnings = moderate_output(page.get('text', ''), age)
            page['text'] = sanitize_html(cleaned_text)
            all_moderation_flags.extend(warnings)

            cleaned_prompt, img_warnings = moderate_image_prompt(page.get('imagePrompt', ''))
            page['imagePrompt'] = cleaned_prompt
            all_moderation_flags.extend(img_warnings)

        if all_moderation_flags:
            logger.warning(f'Moderation flags for story: {all_moderation_flags}')

        db.log_api_call('claude', text_model, True,
                        int((time.time() - start_time) * 1000), user_id=user_id)

        # 2. Generate images with Azure gpt-image-1.5
        azure_img_key = os.environ.get('AZURE_GPT_IMAGE_API_KEY', '')
        azure_img_endpoint = os.environ.get('AZURE_GPT_IMAGE_ENDPOINT', '')

        imagen_start = time.time()
        total_pages = len(story_data['pages'])

        def _make_page_image(idx_page):
            idx, page = idx_page
            img_prompt = build_image_prompt(
                page['imagePrompt'], child_name, age,
                gender, idx + 1, total_pages,
                illustration_style=illustration_style,
                character_description=character_description,
            )
            image_url = None
            if azure_img_key and azure_img_endpoint and _image_storage:
                try:
                    with AIGenerationTracker('azure_gpt_image', 'gpt-image-1.5', page_num=idx + 1):
                        img_bytes = _generate_image_azure_gpt(azure_img_key, azure_img_endpoint, img_prompt)
                    if img_bytes:
                        img_name = f'story_{int(time.time())}_{idx + 1}.png'
                        image_url = _image_storage.save_image(img_bytes, img_name)
                        logger.info(f'Image saved via Azure gpt-image-1.5 (page {idx + 1}): {img_name}')
                    usage_counter.record('azure_gpt_image', success=bool(image_url))
                    db.log_api_call('azure_gpt_image', 'gpt-image-1.5', bool(image_url),
                                    user_id=user_id)
                except Exception as e:
                    print(f'[IMG] page {idx+1} EXCEPTION: {type(e).__name__}: {e}', flush=True)
                    logger.error(f'Azure image generation error page {idx + 1}: {e}')
                    usage_counter.record('azure_gpt_image', success=False)
                    db.log_api_call('azure_gpt_image', 'gpt-image-1.5', False,
                                    error_message=str(e), user_id=user_id)
            return {
                'text': page['text'],
                'imageUrl': image_url,
                'pageNumber': idx + 1,
            }

        # Generate all page images in parallel — biggest latency win.
        max_workers = min(total_pages, 6) or 1
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            pages_with_images = list(pool.map(_make_page_image, enumerate(story_data['pages'])))

        # 3. Save to DB
        generation_time_ms = int((time.time() - start_time) * 1000)
        imagen_ms = int((time.time() - imagen_start) * 1000)
        story = db.create_story(
            child_name=child_name, age=age, gender=gender,
            condition=condition, hero_characteristics=hero_characteristics,
            story_title=story_data.get('title', f"{child_name}'s Brave Adventure"),
            pages=pages_with_images, user_id=user_id,
            child_id=child_id, moderation_flags=all_moderation_flags,
            generation_time_ms=generation_time_ms,
            hero_character=hero_character,
        )

        if not story:
            return jsonify({'message': 'Failed to save story'}), 500

        # Story persisted — the up-front reservation is now committed, so the
        # finally block must not release it.
        usage_reserved = False

        perf_tracker.record_generation(
            story_id=story.get('id', 0),
            claude_ms=claude_ms,
            flux_ms=imagen_ms,
            total_ms=generation_time_ms,
            pages=len(pages_with_images),
        )

        logger.info(f'Story generated in {generation_time_ms}ms: {story.get("storyTitle")}')
        return jsonify(story), 201

    except json.JSONDecodeError as e:
        logger.error(f'JSON parse error: {e}')
        usage_counter.record('claude', success=False)
        perf_tracker.record_error('JSONDecodeError')
        return jsonify({'message': 'Failed to parse story from AI response'}), 500
    except Exception as e:
        logger.error(f'Story generation error: {e}', exc_info=True)
        perf_tracker.record_error(type(e).__name__)
        return jsonify({'message': str(e)}), 500
    finally:
        # Any path that leaves without a committed story (early-return failures
        # or an exception) must release the slot reserved up-front so a failed
        # generation never permanently burns the user's monthly quota.
        if usage_reserved:
            try:
                decrement_usage(user_id, 'storybook')
            except Exception as e:
                logger.warning(f'Failed to release reserved usage slot: {e}')


# ── Feedback & Personalization Routes ─────────────────────────────────

@stories_bp.route('/api/stories/<int:story_id>/pdf', methods=['GET'])
@login_required
@require_feature('pdf_export')
def export_story_pdf(story_id):
    """Render a story as a downloadable PDF (Caregiver+ tier)."""
    story = db.get_story(story_id, user_id=g.user_id)
    if not story:
        return jsonify({'message': 'Story not found'}), 404
    story = _refresh_image_urls(story)

    try:
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib.enums import TA_CENTER
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image as RLImage,
        )
    except ImportError:
        return jsonify({'message': 'PDF export not available — reportlab missing'}), 503

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('cc-title', parent=styles['Title'],
                                 fontSize=24, alignment=TA_CENTER, spaceAfter=20)
    body_style = ParagraphStyle('cc-body', parent=styles['BodyText'],
                                fontSize=13, leading=20, spaceAfter=10)

    elements = [
        Paragraph(story.get('storyTitle') or "A Brave Story", title_style),
        Paragraph(f"For {story.get('childName', '')}", styles['Italic']),
        Spacer(1, 0.6*cm),
    ]

    pages = story.get('pages') or []
    for idx, page in enumerate(pages):
        if idx > 0:
            elements.append(PageBreak())

        img_url = page.get('imageUrl') or ''
        if img_url:
            try:
                if img_url.startswith('http'):
                    resp = requests.get(img_url, timeout=15)
                    resp.raise_for_status()
                    img_data = BytesIO(resp.content)
                else:
                    # Local URL like /generated_images/xxx.png
                    fname = _extract_s3_filename(img_url) or img_url.lstrip('/')
                    local_path = os.path.join(
                        os.path.dirname(__file__), '..', '..', 'client', 'generated_images', fname,
                    )
                    img_data = open(local_path, 'rb')
                img = RLImage(img_data, width=14*cm, height=14*cm, kind='proportional')
                img.hAlign = 'CENTER'
                elements.append(img)
                elements.append(Spacer(1, 0.4*cm))
            except Exception as e:
                logger.warning(f'PDF image embed failed for page {idx + 1}: {e}')

        text = (page.get('text') or '').replace('\n', '<br/>')
        elements.append(Paragraph(text, body_style))

    doc.build(elements)
    buf.seek(0)

    safe_title = ''.join(c for c in (story.get('storyTitle') or 'story')
                         if c.isalnum() or c in ' -_').strip().replace(' ', '_') or 'story'
    return Response(
        buf.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{safe_title}.pdf"'},
    )


@stories_bp.route('/api/stories/<int:story_id>/feedback', methods=['POST'])
@login_required
def submit_feedback(story_id):
    """Record user feedback (rating, favourite page, read time) for a story."""
    data = request.get_json()
    story = db.get_story(story_id, user_id=g.user_id)
    if not story:
        return jsonify({'message': 'Story not found'}), 404

    child_id = story.get('child_id')
    if child_id:
        db.record_story_feedback(
            story_id=story_id, child_id=child_id,
            rating=data.get('rating'),
            favorite_page=data.get('favoritePage'),
            read_time_sec=data.get('readTimeSec', 0),
        )
        if data.get('rating') and data['rating'] >= 4:
            theme = story.get('theme', '')
            if theme:
                db.add_preference(child_id, 'theme', theme, weight=data['rating'] / 5.0)

    return jsonify({'success': True})


@stories_bp.route('/api/stories/<int:story_id>/user-feedback', methods=['POST'])
@login_required
def submit_user_feedback(story_id):
    """Submit user feedback: star rating, emoji reaction, helpful flag, comment."""
    data = request.get_json()
    story = db.get_story(story_id, user_id=g.user_id)
    if not story:
        return jsonify({'message': 'Story not found'}), 404

    user_id = g.user_id

    star_rating = data.get('starRating')
    if star_rating is not None:
        star_rating = int(star_rating)
        if star_rating < 1 or star_rating > 5:
            return jsonify({'message': 'Star rating must be 1-5'}), 400

    emoji = data.get('emojiReaction')
    if emoji and emoji not in ('\U0001f60a', '\U0001f610', '\U0001f622'):
        return jsonify({'message': 'Invalid emoji reaction'}), 400

    is_helpful = data.get('isHelpful')
    comment = (data.get('comment') or '').strip()
    if comment:
        comment = sanitize_html(comment[:500])

    page_number = data.get('pageNumber')

    result = db.submit_user_feedback(
        story_id=story_id, user_id=user_id,
        star_rating=star_rating, emoji_reaction=emoji,
        is_helpful=is_helpful, comment=comment,
        page_number=page_number,
    )
    return jsonify({'success': True, 'feedback': result}), 201


@stories_bp.route('/api/stories/<int:story_id>/user-feedback', methods=['GET'])
@login_required
def get_story_feedback(story_id):
    """Get aggregated feedback summary for a story (only if owned by authenticated user)."""
    story = db.get_story(story_id, user_id=g.user_id)
    if not story:
        return jsonify({'message': 'Story not found'}), 404
    return jsonify(db.get_story_feedback_summary(story_id))


@stories_bp.route('/api/admin/feedback', methods=['GET'])
@login_required
def admin_feedback_stats():
    """Get admin feedback statistics."""
    return jsonify(db.get_admin_feedback_stats())


@stories_bp.route('/api/feedback/overall', methods=['POST'])
@login_required
def submit_overall_feedback():
    """Submit overall platform feedback (not tied to a specific story)."""
    data = request.get_json() or {}
    user_id = getattr(g, 'user_id', None)

    star_rating = data.get('starRating')
    if star_rating is not None:
        star_rating = int(star_rating)
        if star_rating < 1 or star_rating > 5:
            return jsonify({'message': 'Star rating must be 1-5'}), 400

    emoji = data.get('emojiReaction')
    if emoji and emoji not in ('\U0001f60a', '\U0001f610', '\U0001f622'):
        return jsonify({'message': 'Invalid emoji reaction'}), 400

    is_helpful = data.get('isHelpful')
    comment = (data.get('comment') or '').strip()
    if comment:
        comment = sanitize_html(comment[:500])

    result = db.submit_user_feedback(
        story_id=0, user_id=user_id,
        star_rating=star_rating, emoji_reaction=emoji,
        is_helpful=is_helpful, comment=comment,
        page_number=None,
    )
    return jsonify({'success': True, 'feedback': result}), 201


@stories_bp.route('/api/children/<int:child_id>/preferences', methods=['GET'])
@login_required
def get_preferences(child_id):
    """Return learned personalisation preferences for a child (only if owned by authenticated user)."""
    if not db.verify_child_owner(child_id, g.user_id):
        return jsonify({'message': 'Child not found'}), 404
    return jsonify(db.get_preferences(child_id))
