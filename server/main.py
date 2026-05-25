"""
Brave Story Maker — Application Entry Point
─────────────────────────────────────────────
Configures Flask, registers Blueprints, sets up rate limiting,
and serves the single-page client application.
"""

import os
import sys
import time
from pathlib import Path

from flask import Flask, redirect, request, send_from_directory, Response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

BUILD_TS = str(int(time.time()))  # unique on every server restart

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / '.env')

# Add server dir to path for local imports
sys.path.insert(0, os.path.dirname(__file__))

# Database (PostgreSQL + SQLite fallback)
import database_v2 as db

# Logging
from cloud_storage import create_storage
from monitoring import log_request, log_response

# Blueprints
from routes.auth import auth_bp
from routes.stories import stories_bp, init_stories_bp
from routes.health import health_bp, init_health_bp
from routes.credits import credits_bp
from routes.speech import speech_bp
from routes.moonface import moonface_bp
from routes.translation import translation_bp
from routes.subscription import subscription_bp
from routes.analytics import analytics_bp

import logging
logger = logging.getLogger('brave_story.app')

# ── App factory ───────────────────────────────────────────────────────

app = Flask(__name__, static_folder=None)

# ── CORS: restrict to explicit origins (never wildcard in production) ─
_allowed_origins = os.environ.get(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:5000,http://127.0.0.1:5000'
)
CORS(app, origins=[o.strip() for o in _allowed_origins.split(',')],
     supports_credentials=False)

# ── Rate limiting (in-memory; swap to Redis for multi-process) ───────
# No global default_limits — a single page load fans out into ~10 requests
# (HTML + CSS + several JS files + nav-profile API calls), so a global 60/hour
# cap meant a handful of hard refreshes would 429 the asset routes and leave
# the page blank. Apply tight limits only to sensitive endpoints.
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://",
)
limiter.limit("10 per minute")(auth_bp)
# Story generation is expensive — limit only that route, not all story reads


# ── Register Blueprints ──────────────────────────────────────────────
app.register_blueprint(auth_bp)
app.register_blueprint(stories_bp)
app.register_blueprint(health_bp)
app.register_blueprint(credits_bp)
app.register_blueprint(speech_bp)
app.register_blueprint(moonface_bp)
app.register_blueprint(translation_bp)
app.register_blueprint(subscription_bp)
app.register_blueprint(analytics_bp)

# ── Request / response logging ───────────────────────────────────────

@app.before_request
def before_req():
    """Start a request timer for performance logging."""
    log_request()

@app.after_request
def after_req(response):
    """Log method, path, status, and duration of every request."""
    return log_response(response)

@app.after_request
def add_no_cache(response):
    """Prevent browsers from caching API responses."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.after_request
def add_security_headers(response):
    """Add OWASP-recommended security headers to every response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://accounts.google.com/gsi/client; "
        "style-src 'self' 'unsafe-inline' https://accounts.google.com; "
        "img-src 'self' data: blob: https:; "
        "media-src 'self' blob: data:; "
        "font-src 'self' data:; "
        "connect-src 'self' https://accounts.google.com/gsi/; "
        "frame-src https://accounts.google.com/gsi/; "
        "frame-ancestors 'none'"
    )
    response.headers['Permissions-Policy'] = 'camera=(self), microphone=(), geolocation=()'
    return response


# ── Helpers ───────────────────────────────────────────────────────────

def _bust(html):
    """Replace internal page and asset URLs with cache-busted versions."""
    # Assets (CSS / JS)
    for asset in (
        '/css/styles.css', '/css/dashboard.css',
        '/js/home.js', '/js/create.js', '/js/story.js', '/js/auth.js',
        '/js/nav-profile.js', '/js/admin-credits.js', '/js/my-credits.js',
        '/js/feedback.js', '/js/account.js', '/js/profiles.js',
        '/js/balloons.js', '/js/balloons-lib.js',
        '/js/pricing.js', '/js/analytics.js', '/js/usage-widget.js',
    ):
        html = html.replace(f'{asset}"', f'{asset}?v={BUILD_TS}"')
    # Internal page links — prevents stale HTML from the browser cache
    for page in ('create', 'login', 'story', 'admin-credits', 'my-credits', 'feedback', 'account', 'profiles', 'pricing', 'analytics'):
        html = html.replace(f'href="/{page}"', f'href="/{page}?v={BUILD_TS}"')
    html = html.replace('href="/"', f'href="/?v={BUILD_TS}"')
    return html


def serve_html(filename):
    """Serve an HTML file with cache-busted asset and page URLs."""
    html = (CLIENT_DIR / filename).read_text(encoding='utf-8')
    return Response(_bust(html), mimetype='text/html')


# ── Init DB on startup ───────────────────────────────────────────────
db.init_db()

# Static dirs
CLIENT_DIR = Path(__file__).parent.parent / 'client'
IMAGES_DIR = CLIENT_DIR / 'generated_images'
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Initialize cloud storage and inject into blueprints
image_storage = create_storage(str(IMAGES_DIR))
init_stories_bp(image_storage, limiter)
init_health_bp(image_storage)

# ── Static file serving ──────────────────────────────────────────────

def _ensure_version():
    """Redirect bare page URLs to versioned URLs to defeat browser cache."""
    if 'v' not in request.args:
        existing = request.query_string.decode()
        qs = f'{existing}&v={BUILD_TS}' if existing else f'v={BUILD_TS}'
        return redirect(f'{request.path}?{qs}', code=302)
    return None

@app.route('/')
def serve_index():
    """Serve the main landing page."""
    redir = _ensure_version()
    if redir: return redir
    return serve_html('index.html')

@app.route('/create')
def serve_create():
    """Serve the story creation page."""
    redir = _ensure_version()
    if redir: return redir
    return serve_html('create.html')

@app.route('/login')
def serve_login():
    """Serve the login / registration page."""
    redir = _ensure_version()
    if redir: return redir
    return serve_html('login.html')

@app.route('/story/<int:story_id>')
def serve_story(**_):
    """Serve the story reader page."""
    redir = _ensure_version()
    if redir: return redir
    return serve_html('story.html')

@app.route('/admin-credits')
def serve_admin_credits():
    """Serve the admin credit dashboard."""
    redir = _ensure_version()
    if redir: return redir
    return serve_html('admin-credits.html')

@app.route('/my-credits')
def serve_my_credits():
    """Serve the user credit dashboard."""
    redir = _ensure_version()
    if redir: return redir
    return serve_html('my-credits.html')

@app.route('/feedback')
def serve_feedback():
    """Serve the help & support / feedback page."""
    redir = _ensure_version()
    if redir: return redir
    return serve_html('feedback.html')

@app.route('/account')
def serve_account():
    """Serve the account settings page."""
    redir = _ensure_version()
    if redir: return redir
    return serve_html('account.html')

@app.route('/profiles')
def serve_profiles():
    """Serve the hero profile selection page."""
    redir = _ensure_version()
    if redir: return redir
    return serve_html('profiles.html')

@app.route('/pricing')
def serve_pricing():
    """Serve the subscription pricing page."""
    redir = _ensure_version()
    if redir: return redir
    return serve_html('pricing.html')

@app.route('/analytics')
def serve_analytics():
    """Serve the Hospital tier engagement analytics dashboard."""
    redir = _ensure_version()
    if redir: return redir
    return serve_html('analytics.html')

@app.route('/css/<path:filename>')
def serve_css(filename):
    """Serve CSS assets from the client directory."""
    return send_from_directory(CLIENT_DIR / 'css', filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    """Serve JavaScript assets with cache-busted page URLs."""
    js_path = CLIENT_DIR / 'js' / filename
    content = js_path.read_text(encoding='utf-8')
    # Bust internal page links embedded in JS-generated HTML
    for page in ('create', 'login', 'story', 'admin-credits', 'my-credits', 'feedback', 'account', 'profiles', 'pricing', 'analytics'):
        content = content.replace(f'href="/{page}"', f'href="/{page}?v={BUILD_TS}"')
    content = content.replace('href="/"', f'href="/?v={BUILD_TS}"')
    return Response(content, mimetype='application/javascript')

@app.route('/generated_images/<path:filename>')
def serve_image(filename):
    """Serve generated story images."""
    return send_from_directory(IMAGES_DIR, filename)

@app.route('/images/<path:filename>')
def serve_static_image(filename):
    """Serve static UI images from client/images/."""
    return send_from_directory(CLIENT_DIR / 'images', filename)

# ── Entry point ───────────────────────────────────────────────────────

if __name__ == '__main__':
    logger.info('Brave Story Maker server starting...')
    logger.info(f'Serving client from: {CLIENT_DIR}')
    logger.info(f'Storage backend: {image_storage.__class__.__name__}')
    debug = os.environ.get('FLASK_DEBUG', '1') == '1'
    port = int(os.environ.get('PORT', '5002'))
    app.run(host='0.0.0.0', port=port, debug=debug)
