"""
Monitoring & Logging System
────────────────────────────
Structured logging for AI generation, API usage, errors, and performance metrics.
"""

import os
import sys
import time
import json
import logging
import logging.handlers
import threading
from collections import deque
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import request, g

# ── Log directory setup ──────────────────────────────────────────────
LOG_DIR = Path(__file__).parent.parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# ── Server start time (for uptime) ──────────────────────────────────
SERVER_START_TIME = time.time()

# ── Structured JSON formatter ────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Format log records as JSON for easy parsing."""

    def format(self, record):
        log_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        # Add extra fields if present
        for key in ['user_id', 'story_id', 'api', 'duration_ms',
                     'status_code', 'method', 'path', 'error_type',
                     'generation_id', 'page_num', 'model', 'tokens_used']:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)

        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_data)


# ── Configure logging ────────────────────────────────────────────────

def setup_logging():
    """Configure application-wide logging."""
    root_logger = logging.getLogger('brave_story')
    root_logger.setLevel(logging.DEBUG)

    # Console handler (human-readable)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    ))
    root_logger.addHandler(console)

    # File handler - general logs (rotating, 5MB per file, 10 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / 'app.log', maxBytes=5_000_000, backupCount=10, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)

    # File handler - errors only
    error_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / 'errors.log', maxBytes=5_000_000, backupCount=10, encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(error_handler)

    # File handler - AI generation logs
    ai_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / 'ai_generation.log', maxBytes=5_000_000, backupCount=10, encoding='utf-8'
    )
    ai_handler.setLevel(logging.DEBUG)
    ai_handler.setFormatter(JSONFormatter())
    ai_logger = logging.getLogger('brave_story.ai')
    ai_logger.addHandler(ai_handler)

    # File handler - API usage
    api_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / 'api_usage.log', maxBytes=5_000_000, backupCount=10, encoding='utf-8'
    )
    api_handler.setLevel(logging.INFO)
    api_handler.setFormatter(JSONFormatter())
    api_logger = logging.getLogger('brave_story.api')
    api_logger.addHandler(api_handler)

    return root_logger


# ── Loggers ──────────────────────────────────────────────────────────
app_logger = logging.getLogger('brave_story')
ai_logger = logging.getLogger('brave_story.ai')
api_logger = logging.getLogger('brave_story.api')
auth_logger = logging.getLogger('brave_story.auth')
safety_logger = logging.getLogger('brave_story.content_safety')


# ── Request/Response logging middleware ──────────────────────────────

def log_request():
    """Call this in Flask before_request."""
    g.request_start = time.time()


def log_response(response):
    """Call this in Flask after_request."""
    duration_ms = int((time.time() - getattr(g, 'request_start', time.time())) * 1000)
    user_id = getattr(g, 'user_id', None)

    is_error = response.status_code >= 400
    perf_tracker.record_request(is_error=is_error)

    api_logger.info(
        f'{request.method} {request.path} → {response.status_code} ({duration_ms}ms)',
        extra={
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'duration_ms': duration_ms,
            'user_id': user_id,
        }
    )
    return response


# ── AI Generation tracking ──────────────────────────────────────────

class AIGenerationTracker:
    """Context manager for tracking AI generation calls."""

    def __init__(self, api_name: str, model: str = '', **extra):
        self.api_name = api_name
        self.model = model
        self.extra = extra
        self.start_time = time.time()

    def __enter__(self):
        ai_logger.info(
            f'Starting {self.api_name} generation',
            extra={'api': self.api_name, 'model': self.model, **self.extra}
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.time() - self.start_time) * 1000)

        if exc_type:
            ai_logger.error(
                f'{self.api_name} generation FAILED after {duration_ms}ms: {exc_val}',
                extra={
                    'api': self.api_name,
                    'model': self.model,
                    'duration_ms': duration_ms,
                    'error_type': exc_type.__name__,
                    **self.extra
                }
            )
        else:
            ai_logger.info(
                f'{self.api_name} generation completed in {duration_ms}ms',
                extra={
                    'api': self.api_name,
                    'model': self.model,
                    'duration_ms': duration_ms,
                    **self.extra
                }
            )
        return False  # Don't suppress exceptions


def track_ai_call(api_name: str, model: str = ''):
    """Decorator for tracking AI API calls."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            with AIGenerationTracker(api_name, model):
                return f(*args, **kwargs)
        return wrapped
    return decorator


# ── API Usage counter (in-memory, persisted to file) ────────────────

class APIUsageCounter:
    """Track API call counts and costs."""

    def __init__(self):
        self.counts = {}
        self.usage_file = LOG_DIR / 'api_usage_counts.json'
        # Guards self.counts and the file write — parallel image workers
        # (ThreadPoolExecutor in generate_story) call record() concurrently.
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if self.usage_file.exists():
            try:
                self.counts = json.loads(self.usage_file.read_text())
            except Exception:
                self.counts = {}

    def _save(self):
        # Callers already hold self._lock.
        try:
            self.usage_file.write_text(json.dumps(self.counts, indent=2))
        except Exception as e:
            app_logger.error(f'Failed to save API usage counts: {e}')

    def record(self, api_name: str, success: bool = True,
               tokens: int = 0, cost_usd: float = 0.0):
        """Record a single API call for today's usage counters."""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        key = f'{today}:{api_name}'

        with self._lock:
            if key not in self.counts:
                self.counts[key] = {
                    'date': today,
                    'api': api_name,
                    'total_calls': 0,
                    'success': 0,
                    'failures': 0,
                    'total_tokens': 0,
                    'total_cost_usd': 0.0,
                }

            self.counts[key]['total_calls'] += 1
            if success:
                self.counts[key]['success'] += 1
            else:
                self.counts[key]['failures'] += 1
            self.counts[key]['total_tokens'] += tokens
            self.counts[key]['total_cost_usd'] += cost_usd
            self._save()

    def get_today_stats(self):
        """Return usage counters scoped to today (UTC)."""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        with self._lock:
            return {k: v for k, v in self.counts.items() if k.startswith(today)}

    def get_all_stats(self):
        """Return all recorded usage stats across all days."""
        with self._lock:
            return dict(self.counts)


# Singleton counter
usage_counter = APIUsageCounter()


# ── Performance Metrics ─────────────────────────────────────────────

class PerformanceTracker:
    """Track generation timing breakdowns and error rates."""

    def __init__(self, max_history=200):
        self._generation_times = deque(maxlen=max_history)
        self._error_counts = {'total': 0, 'by_type': {}}
        self._request_count = 0
        self._error_request_count = 0

    def record_generation(self, story_id, claude_ms=0, flux_ms=0, total_ms=0, pages=0):
        self._generation_times.append({
            'story_id': story_id,
            'claude_ms': claude_ms,
            'flux_ms': flux_ms,
            'total_ms': total_ms,
            'pages': pages,
            'ts': datetime.now(timezone.utc).isoformat(),
        })

    def record_error(self, error_type):
        self._error_counts['total'] += 1
        self._error_counts['by_type'][error_type] = \
            self._error_counts['by_type'].get(error_type, 0) + 1

    def record_request(self, is_error=False):
        self._request_count += 1
        if is_error:
            self._error_request_count += 1

    def get_metrics(self):
        uptime_s = int(time.time() - SERVER_START_TIME)
        mem_mb = _get_memory_mb()

        # Compute generation averages
        times = list(self._generation_times)
        avg_claude = avg_flux = avg_total = 0
        if times:
            avg_claude = int(sum(t['claude_ms'] for t in times) / len(times))
            avg_flux = int(sum(t['flux_ms'] for t in times) / len(times))
            avg_total = int(sum(t['total_ms'] for t in times) / len(times))

        error_rate = 0.0
        if self._request_count > 0:
            error_rate = round(self._error_request_count / self._request_count * 100, 2)

        return {
            'uptime_seconds': uptime_s,
            'uptime_human': _format_uptime(uptime_s),
            'memory_mb': mem_mb,
            'python_version': sys.version.split()[0],
            'total_requests': self._request_count,
            'error_rate_pct': error_rate,
            'errors': self._error_counts,
            'generation_avg': {
                'claude_ms': avg_claude,
                'flux_ms': avg_flux,
                'total_ms': avg_total,
                'sample_size': len(times),
            },
            'recent_generations': list(times)[-10:],
        }


def _get_memory_mb():
    import sys
    if sys.platform != 'win32':
        try:
            import resource  # type: ignore[import-not-found]
            return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        except ImportError:
            pass
    try:
        import psutil
        return round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 1)
    except ImportError:
        return 0


def _format_uptime(seconds):
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days: parts.append(f'{days}d')
    if hours: parts.append(f'{hours}h')
    if minutes: parts.append(f'{minutes}m')
    parts.append(f'{secs}s')
    return ' '.join(parts)


# Singleton performance tracker
perf_tracker = PerformanceTracker()
