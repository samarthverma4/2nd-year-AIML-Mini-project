"""
Database Layer (PostgreSQL + SQLite fallback)
─────────────────────────────────────────────
Supports PostgreSQL for production and SQLite for local development.
Includes: users, children profiles, stories, personalization preferences.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List
from contextlib import contextmanager

logger = logging.getLogger('brave_story.database')

# ── Determine database backend ───────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')
USE_POSTGRES = DATABASE_URL.startswith('postgres')

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
    logger.info(f'Using PostgreSQL: {DATABASE_URL[:30]}...')
else:
    import sqlite3
    DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'stories.db')
    logger.info(f'Using SQLite: {DB_PATH}')


# ── Connection management ────────────────────────────────────────────

@contextmanager
def get_db():
    """Get a database connection (PostgreSQL or SQLite)."""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _execute(conn, sql, params=None):
    """Execute a SQL statement, automatically translating ``?``
    placeholders to ``%s`` when running against PostgreSQL.

    Args:
        conn: Active database connection.
        sql: SQL statement (use ``?`` for parameter placeholders).
        params: Optional tuple/list of query parameters.

    Returns:
        A database cursor after execution.
    """
    if USE_POSTGRES:
        # Convert ? to %s for psycopg2
        sql = sql.replace('?', '%s')
        # Convert AUTOINCREMENT to SERIAL
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        sql = sql.replace("datetime('now')", "NOW()")
    cur = conn.cursor()
    cur.execute(sql, params or ())
    return cur


def _fetchone(conn, sql, params=None):
    """Execute *sql* and return the first row as a dict, or ``None``."""
    cur = _execute(conn, sql, params)
    if USE_POSTGRES:
        cols = [desc[0] for desc in cur.description] if cur.description else []
        row = cur.fetchone()
        return dict(zip(cols, row)) if row else None
    else:
        return cur.fetchone()


def _fetchall(conn, sql, params=None):
    """Execute *sql* and return all rows as a list of dicts."""
    cur = _execute(conn, sql, params)
    if USE_POSTGRES:
        cols = [desc[0] for desc in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    else:
        return cur.fetchall()


# ── Schema initialization ────────────────────────────────────────────

def init_db():
    """Create all tables."""
    with get_db() as conn:
        # Users table
        _execute(conn, '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                last_login TEXT
            )
        ''')

        # Migrate: add google_id column if it doesn't exist yet
        try:
            _execute(conn, 'ALTER TABLE users ADD COLUMN google_id TEXT')
        except Exception:
            pass  # column already exists

        # Children profiles (linked to parent user)
        _execute(conn, '''
            CREATE TABLE IF NOT EXISTS children (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                gender TEXT NOT NULL DEFAULT 'neutral',
                conditions TEXT DEFAULT '[]',
                preferences TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # Migrate: add hero customization columns to children
        for _col, _def in [
            ('medical_challenge', "TEXT DEFAULT ''"),
            ('characteristics',   "TEXT DEFAULT ''"),
            ('hero_character',    'TEXT DEFAULT NULL'),
        ]:
            try:
                _execute(conn, f'ALTER TABLE children ADD COLUMN {_col} {_def}')
            except Exception:
                pass  # column already exists

        # Stories table (extended with user_id)
        _execute(conn, '''
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                child_id INTEGER,
                child_name TEXT NOT NULL,
                age INTEGER NOT NULL,
                gender TEXT NOT NULL,
                condition TEXT NOT NULL,
                hero_characteristics TEXT,
                story_title TEXT,
                pages TEXT NOT NULL DEFAULT '[]',
                is_favorite INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                moderation_flags TEXT DEFAULT '[]',
                generation_time_ms INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE SET NULL
            )
        ''')

        # Personalization preferences (learning over time)
        _execute(conn, '''
            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                child_id INTEGER NOT NULL,
                preference_type TEXT NOT NULL,
                preference_value TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
            )
        ''')

        # Story feedback (for personalization learning)
        _execute(conn, '''
            CREATE TABLE IF NOT EXISTS story_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER NOT NULL,
                child_id INTEGER,
                rating INTEGER,
                favorite_page INTEGER,
                read_count INTEGER DEFAULT 1,
                total_read_time_sec INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE SET NULL
            )
        ''')

        # User feedback (ratings, emoji reactions, text comments)
        _execute(conn, '''
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER NOT NULL,
                user_id INTEGER,
                star_rating INTEGER,
                emoji_reaction TEXT,
                is_helpful INTEGER,
                comment TEXT,
                page_number INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')

        # API usage log table
        _execute(conn, '''
            CREATE TABLE IF NOT EXISTS api_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_name TEXT NOT NULL,
                model TEXT,
                success INTEGER NOT NULL DEFAULT 1,
                duration_ms INTEGER,
                tokens_used INTEGER DEFAULT 0,
                credits_used REAL DEFAULT 0.0,
                error_message TEXT,
                user_id INTEGER,
                story_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        # Credit configuration table (admin-managed)
        _execute(conn, '''
            CREATE TABLE IF NOT EXISTS credit_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT UNIQUE NOT NULL,
                config_value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        # Insert default credit config if not exists
        existing = _fetchone(conn,
            "SELECT id FROM credit_config WHERE config_key = 'total_budget'")
        if not existing:
            _execute(conn,
                "INSERT INTO credit_config (config_key, config_value) VALUES ('total_budget', '1000')")
            _execute(conn,
                "INSERT INTO credit_config (config_key, config_value) VALUES ('flux2pro_cost_per_image', '0.05')")
            _execute(conn,
                "INSERT INTO credit_config (config_key, config_value) VALUES ('claude_cost_per_call', '0.01')")

        # Migrate legacy gemini_cost_per_call rows to claude_cost_per_call
        legacy = _fetchone(conn,
            "SELECT config_value FROM credit_config WHERE config_key = 'gemini_cost_per_call'")
        if legacy:
            existing_claude = _fetchone(conn,
                "SELECT id FROM credit_config WHERE config_key = 'claude_cost_per_call'")
            if not existing_claude:
                _execute(conn,
                    "INSERT INTO credit_config (config_key, config_value) VALUES ('claude_cost_per_call', ?)",
                    (legacy['config_value'],))
            _execute(conn,
                "DELETE FROM credit_config WHERE config_key = 'gemini_cost_per_call'")

        # ── Subscription tables & migrations ──────────────────────────
        for _col, _def in [
            ('subscription_tier',         "TEXT NOT NULL DEFAULT 'free'"),
            ('subscription_status',       "TEXT NOT NULL DEFAULT 'active'"),
            ('subscription_expires_at',   'TEXT'),
            ('razorpay_subscription_id',  'TEXT'),
            ('organisation_id',           'INTEGER'),
        ]:
            try:
                _execute(conn, f'ALTER TABLE users ADD COLUMN {_col} {_def}')
            except Exception:
                pass

        _execute(conn, '''
            CREATE TABLE IF NOT EXISTS usage_counters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                storybooks_generated INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, month),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        _execute(conn, '''
            CREATE TABLE IF NOT EXISTS organisations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                logo_url TEXT,
                hospital_plan_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        _execute(conn, '''
            CREATE TABLE IF NOT EXISTS payment_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                razorpay_payment_id TEXT,
                razorpay_order_id TEXT,
                amount_paise INTEGER,
                tier TEXT,
                status TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # ── Migrations: add missing columns to existing SQLite tables ──
        if not USE_POSTGRES:
            migrations = [
                ('stories', 'user_id',              'INTEGER'),
                ('stories', 'child_id',             'INTEGER'),
                ('stories', 'hero_characteristics',  'TEXT'),
                ('stories', 'moderation_flags',     "TEXT DEFAULT '[]'"),
                ('stories', 'generation_time_ms',   'INTEGER DEFAULT 0'),
                ('api_logs', 'user_id',             'INTEGER'),
                ('api_logs', 'story_id',            'INTEGER'),
                ('api_logs', 'credits_used',        'REAL DEFAULT 0.0'),
                ('users',   'is_admin',             'INTEGER DEFAULT 0'),
                ('stories', 'hero_character',        'TEXT'),
            ]
            cur = conn.cursor()
            for table, column, col_def in migrations:
                # Safe: table/column/col_def are hardcoded literals above, not user input
                cur.execute(f'PRAGMA table_info({table})')
                existing = [row[1] for row in cur.fetchall()]
                if column not in existing:
                    cur.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_def}')
                    logger.info(f'Migration: added column {table}.{column}')

    logger.info('Database initialized successfully')


# ── Row converters ───────────────────────────────────────────────────

def _row_to_dict(row) -> Optional[dict]:
    """Convert a row to a dict (works for both SQLite Row and PG dict)."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def row_to_story(row) -> Optional[dict]:
    """Convert a raw story DB row into an API-friendly dict."""
    d = _row_to_dict(row)
    if d is None:
        return None
    d['pages'] = json.loads(d['pages']) if isinstance(d['pages'], str) else d['pages']
    d['isFavorite'] = bool(d.pop('is_favorite', 0))
    d['childName'] = d.pop('child_name', '')
    d['heroCharacteristics'] = d.pop('hero_characteristics', '') or ''
    d['storyTitle'] = d.pop('story_title', '') or ''
    d['createdAt'] = d.pop('created_at', '') or ''
    # Expose hero_character as parsed JSON (or None)
    hc = d.pop('hero_character', None)
    if hc and isinstance(hc, str):
        try:
            hc = json.loads(hc)
        except (json.JSONDecodeError, TypeError):
            hc = None
    d['heroCharacter'] = hc
    d.pop('moderation_flags', None)
    d.pop('generation_time_ms', None)
    return d


def row_to_user(row) -> Optional[dict]:
    """Convert a raw user DB row into an API-friendly dict (strips password)."""
    d = _row_to_dict(row)
    if d is None:
        return None
    pw_hash = d.pop('password_hash', '') or ''
    d.pop('salt', None)
    google_id = d.pop('google_id', None)
    d['createdAt'] = d.pop('created_at', '') or ''
    d['lastLogin'] = d.pop('last_login', '') or ''
    # True when the account was created via Google and has no local password
    d['isGoogleUser'] = bool(google_id) and pw_hash == ''
    return d


def row_to_child(row) -> Optional[dict]:
    """Convert a raw child DB row into an API-friendly dict."""
    d = _row_to_dict(row)
    if d is None:
        return None
    d['conditions'] = json.loads(d['conditions']) if isinstance(d['conditions'], str) else (d['conditions'] or [])
    d['preferences'] = json.loads(d['preferences']) if isinstance(d['preferences'], str) else (d['preferences'] or {})
    raw_hc = d.pop('hero_character', None)
    d['heroCharacter'] = json.loads(raw_hc) if raw_hc else None
    d['medicalChallenge'] = d.pop('medical_challenge', '') or ''
    d['characteristics'] = d.get('characteristics', '') or ''
    d['createdAt'] = d.pop('created_at', '') or ''
    d.pop('user_id', None)
    return d


# ── User operations ──────────────────────────────────────────────────

def create_user(email: str, name: str, password_hash: str, salt: str) -> Optional[dict]:
    """Insert a new user and return the created user dict."""
    with get_db() as conn:
        _execute(conn,
            'INSERT INTO users (email, name, password_hash, salt) VALUES (?, ?, ?, ?)',
            (email, name, password_hash, salt)
        )
        row = _fetchone(conn, 'SELECT * FROM users WHERE email = ?', (email,))
        return row_to_user(row)


def get_user_by_email(email: str) -> Optional[dict]:
    """Look up a user by email. Returns full row including password_hash."""
    with get_db() as conn:
        row = _fetchone(conn, 'SELECT * FROM users WHERE email = ?', (email,))
        return _row_to_dict(row)


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Look up a user by primary key, stripping sensitive fields."""
    with get_db() as conn:
        row = _fetchone(conn, 'SELECT * FROM users WHERE id = ?', (user_id,))
        return row_to_user(row)  # type: ignore[return-value]


def update_last_login(user_id: int):
    """Set the user's ``last_login`` timestamp to now (UTC)."""
    with get_db() as conn:
        now = datetime.now(timezone.utc).isoformat()
        _execute(conn, 'UPDATE users SET last_login = ? WHERE id = ?', (now, user_id))


def get_user_by_google_id(google_id: str) -> Optional[dict]:
    """Look up a user by their Google account ID."""
    with get_db() as conn:
        row = _fetchone(conn, 'SELECT * FROM users WHERE google_id = ?', (google_id,))
        return _row_to_dict(row)


def create_google_user(email: str, name: str, google_id: str) -> Optional[dict]:
    """Create a user account linked to a Google identity (no local password)."""
    with get_db() as conn:
        _execute(conn,
            'INSERT INTO users (email, name, password_hash, salt, google_id) VALUES (?, ?, ?, ?, ?)',
            (email, name, '', '', google_id)
        )
        row = _fetchone(conn, 'SELECT * FROM users WHERE email = ?', (email,))
        return row_to_user(row)


def link_google_id(user_id: int, google_id: str) -> None:
    """Attach a Google ID to an existing email/password account."""
    with get_db() as conn:
        _execute(conn, 'UPDATE users SET google_id = ? WHERE id = ?', (google_id, user_id))


def update_user_name(user_id: int, name: str) -> Optional[dict]:
    """Update a user's display name. Returns the updated user dict."""
    with get_db() as conn:
        _execute(conn, 'UPDATE users SET name = ? WHERE id = ?', (name, user_id))
        row = _fetchone(conn, 'SELECT * FROM users WHERE id = ?', (user_id,))
        return row_to_user(row)


def update_user_password(user_id: int, password_hash: str, salt: str) -> bool:
    """Replace a user's password hash and salt. Returns True on success."""
    with get_db() as conn:
        cur = _execute(conn,
            'UPDATE users SET password_hash = ?, salt = ? WHERE id = ?',
            (password_hash, salt, user_id),
        )
        return cur.rowcount > 0


def delete_user(user_id: int) -> bool:
    """Delete a user account and all associated data. Returns True on success."""
    with get_db() as conn:
        # Cascade: remove children, stories, feedback, preferences, api_logs
        _execute(conn, 'DELETE FROM story_feedback WHERE story_id IN (SELECT id FROM stories WHERE user_id = ?)', (user_id,))
        _execute(conn, 'DELETE FROM stories WHERE user_id = ?', (user_id,))
        _execute(conn, 'DELETE FROM preferences WHERE child_id IN (SELECT id FROM children WHERE user_id = ?)', (user_id,))
        _execute(conn, 'DELETE FROM children WHERE user_id = ?', (user_id,))
        _execute(conn, 'DELETE FROM user_feedback WHERE user_id = ?', (user_id,))
        _execute(conn, 'DELETE FROM api_logs WHERE user_id = ?', (user_id,))
        cur = _execute(conn, 'DELETE FROM users WHERE id = ?', (user_id,))
        return cur.rowcount > 0


# ── Children profile operations ──────────────────────────────────────

def create_child(user_id: int, name: str, age: int, gender: str,
                 conditions: Optional[list] = None,
                 medical_challenge: str = '',
                 characteristics: str = '',
                 hero_character: Optional[dict] = None) -> Optional[dict]:
    with get_db() as conn:
        _execute(conn,
            '''INSERT INTO children
               (user_id, name, age, gender, conditions, medical_challenge, characteristics, hero_character)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, name, age, gender, json.dumps(conditions or []),
             medical_challenge, characteristics,
             json.dumps(hero_character) if hero_character else None)
        )
        rows = _fetchall(conn,
            'SELECT * FROM children WHERE user_id = ? ORDER BY id DESC LIMIT 1',
            (user_id,)
        )
        return row_to_child(rows[0]) if rows else None  # type: ignore[return-value]


def get_children(user_id: int) -> list:
    with get_db() as conn:
        rows = _fetchall(conn,
            'SELECT * FROM children WHERE user_id = ? ORDER BY name',
            (user_id,)
        )
        return [row_to_child(r) for r in rows]


def get_child(child_id: int, user_id: Optional[int] = None) -> Optional[dict]:
    if not user_id:
        raise ValueError('get_child requires user_id for ownership scoping')
    with get_db() as conn:
        row = _fetchone(conn, 'SELECT * FROM children WHERE id = ? AND user_id = ?', (child_id, user_id))
        return row_to_child(row) if row else None


def update_child(child_id: int, user_id: Optional[int] = None, **kwargs) -> Optional[dict]:
    if not user_id:
        raise ValueError('update_child requires user_id for ownership scoping')
    # Whitelist of allowed column names — prevents SQL injection via key names
    ALLOWED_COLUMNS = {'name', 'age', 'gender', 'conditions', 'preferences',
                       'medical_challenge', 'characteristics', 'hero_character'}
    updates = {k: v for k, v in kwargs.items() if k in ALLOWED_COLUMNS}
    if not updates:
        if not verify_child_owner(child_id, user_id):
            return None
        return get_child(child_id, user_id=user_id)

    if 'conditions' in updates:
        updates['conditions'] = json.dumps(updates['conditions'])
    if 'preferences' in updates:
        updates['preferences'] = json.dumps(updates['preferences'])
    if 'hero_character' in updates and isinstance(updates['hero_character'], dict):
        updates['hero_character'] = json.dumps(updates['hero_character'])
    elif 'hero_character' in updates and updates['hero_character'] is None:
        updates['hero_character'] = None

    with get_db() as conn:
        # Safe: keys are validated against ALLOWED_COLUMNS above
        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values()) + [child_id, user_id]
        _execute(conn, f'UPDATE children SET {set_clause} WHERE id = ? AND user_id = ?', values)
        row = _fetchone(conn, 'SELECT * FROM children WHERE id = ? AND user_id = ?', (child_id, user_id))
        return row_to_child(row) if row else None


def delete_child(child_id: int, user_id: Optional[int] = None) -> bool:
    if not user_id:
        raise ValueError('delete_child requires user_id for ownership scoping')
    with get_db() as conn:
        cur = _execute(conn, 'DELETE FROM children WHERE id = ? AND user_id = ?', (child_id, user_id))
        return cur.rowcount > 0


def verify_child_owner(child_id: int, user_id: int) -> bool:
    """Check if a child profile belongs to the given user."""
    with get_db() as conn:
        row = _fetchone(conn, 'SELECT id FROM children WHERE id = ? AND user_id = ?', (child_id, user_id))
        return row is not None


# ── Story operations (extended) ──────────────────────────────────────

def create_story(child_name: str, age: int, gender: str, condition: str,
                 hero_characteristics: str, story_title: str, pages: list,
                 user_id: Optional[int] = None, child_id: Optional[int] = None,
                 moderation_flags: Optional[list] = None, generation_time_ms: int = 0,
                 hero_character=None) -> Optional[dict]:
    with get_db() as conn:
        _execute(conn,
            '''INSERT INTO stories (user_id, child_id, child_name, age, gender, condition,
               hero_characteristics, story_title, pages, moderation_flags, generation_time_ms,
               hero_character)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, child_id, child_name, age, gender, condition,
             hero_characteristics, story_title, json.dumps(pages),
             json.dumps(moderation_flags or []), generation_time_ms,
             json.dumps(hero_character) if hero_character else None)
        )
        # Get the newly created story
        rows = _fetchall(conn, 'SELECT * FROM stories ORDER BY id DESC LIMIT 1')
        return row_to_story(rows[0]) if rows else None


def get_story(story_id: int, user_id: Optional[int] = None) -> Optional[dict]:
    if not user_id:
        raise ValueError('get_story requires user_id for ownership scoping')
    with get_db() as conn:
        row = _fetchone(conn, 'SELECT * FROM stories WHERE id = ? AND user_id = ?', (story_id, user_id))
        return row_to_story(row) if row else None


def get_stories(user_id: Optional[int] = None) -> list:
    if not user_id:
        raise ValueError('get_stories requires user_id for ownership scoping')
    with get_db() as conn:
        rows = _fetchall(conn,
            'SELECT * FROM stories WHERE user_id = ? ORDER BY id DESC',
            (user_id,)
        )
        return [row_to_story(r) for r in rows]


def get_favorite_stories(user_id: Optional[int] = None) -> list:
    if not user_id:
        raise ValueError('get_favorite_stories requires user_id for ownership scoping')
    with get_db() as conn:
        rows = _fetchall(conn,
            'SELECT * FROM stories WHERE is_favorite = 1 AND user_id = ? ORDER BY id DESC',
            (user_id,)
        )
        return [row_to_story(r) for r in rows]


def toggle_favorite(story_id: int, user_id: Optional[int] = None) -> Optional[dict]:
    if not user_id:
        raise ValueError('toggle_favorite requires user_id for ownership scoping')
    with get_db() as conn:
        row = _fetchone(conn, 'SELECT * FROM stories WHERE id = ? AND user_id = ?', (story_id, user_id))
        if not row:
            return None
        d = _row_to_dict(row)
        if d is None:
            return None
        new_val = 0 if d.get('is_favorite') else 1
        _execute(conn, 'UPDATE stories SET is_favorite = ? WHERE id = ? AND user_id = ?', (new_val, story_id, user_id))
        row = _fetchone(conn, 'SELECT * FROM stories WHERE id = ? AND user_id = ?', (story_id, user_id))
        return row_to_story(row)


def delete_story(story_id: int, user_id: Optional[int] = None) -> bool:
    if not user_id:
        raise ValueError('delete_story requires user_id for ownership scoping')
    with get_db() as conn:
        cur = _execute(conn, 'DELETE FROM stories WHERE id = ? AND user_id = ?', (story_id, user_id))
        return cur.rowcount > 0


# ── Personalization operations ───────────────────────────────────────

def add_preference(child_id: int, pref_type: str, pref_value: str,
                   weight: float = 1.0) -> Optional[dict]:
    with get_db() as conn:
        _execute(conn,
            'INSERT INTO preferences (child_id, preference_type, preference_value, weight) VALUES (?, ?, ?, ?)',
            (child_id, pref_type, pref_value, weight)
        )
        rows = _fetchall(conn,
            'SELECT * FROM preferences WHERE child_id = ? ORDER BY id DESC LIMIT 1',
            (child_id,)
        )
        return _row_to_dict(rows[0]) if rows else None


def get_preferences(child_id: int) -> list:
    with get_db() as conn:
        rows = _fetchall(conn,
            '''SELECT preference_type, preference_value,
                      SUM(weight) as total_weight, COUNT(*) as count
               FROM preferences WHERE child_id = ?
               GROUP BY preference_type, preference_value
               ORDER BY total_weight DESC''',
            (child_id,)
        )
        return [_row_to_dict(r) for r in rows]


def record_story_feedback(story_id: int, child_id: Optional[int] = None,
                          rating: Optional[int] = None, favorite_page: Optional[int] = None,
                          read_time_sec: int = 0):
    with get_db() as conn:
        existing = _fetchone(conn,
            'SELECT * FROM story_feedback WHERE story_id = ?',
            (story_id,)
        )
        if existing:
            d = _row_to_dict(existing)
            _execute(conn,
                '''UPDATE story_feedback SET
                   read_count = read_count + 1,
                   total_read_time_sec = total_read_time_sec + ?,
                   rating = COALESCE(?, rating),
                   favorite_page = COALESCE(?, favorite_page)
                   WHERE story_id = ?''',
                (read_time_sec, rating, favorite_page, story_id)
            )
        else:
            _execute(conn,
                '''INSERT INTO story_feedback
                   (story_id, child_id, rating, favorite_page, total_read_time_sec)
                   VALUES (?, ?, ?, ?, ?)''',
                (story_id, child_id, rating, favorite_page, read_time_sec)
            )


def get_child_story_history(child_id: int) -> list:
    """Get story history with feedback for a child — used for personalization."""
    with get_db() as conn:
        rows = _fetchall(conn,
            '''SELECT s.*, sf.rating, sf.read_count, sf.favorite_page, sf.total_read_time_sec
               FROM stories s
               LEFT JOIN story_feedback sf ON s.id = sf.story_id
               WHERE s.child_id = ?
               ORDER BY s.id DESC
               LIMIT 20''',
            (child_id,)
        )
        return [_row_to_dict(r) for r in rows]


# ── API log operations ───────────────────────────────────────────────

def log_api_call(api_name: str, model: str = '', success: bool = True,
                 duration_ms: int = 0, tokens_used: int = 0,
                 error_message: str = '', user_id: Optional[int] = None,
                 story_id: Optional[int] = None, credits_used: float = 0.0):
    try:
        # Auto-calculate credits if not provided and call succeeded
        if credits_used == 0.0 and success:
            credits_used = get_credit_cost(api_name)
        with get_db() as conn:
            _execute(conn,
                '''INSERT INTO api_logs
                   (api_name, model, success, duration_ms, tokens_used,
                    error_message, user_id, story_id, credits_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (api_name, model, int(success), duration_ms, tokens_used,
                 error_message, user_id, story_id, credits_used)
            )
    except Exception as e:
        logger.error(f'Failed to log API call: {e}')


def get_api_usage_stats(days: int = 7) -> list:
    with get_db() as conn:
        rows = _fetchall(conn,
            '''SELECT api_name, COUNT(*) as total_calls,
                      SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                      SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures,
                      AVG(duration_ms) as avg_duration_ms,
                      SUM(tokens_used) as total_tokens
               FROM api_logs
               GROUP BY api_name
               ORDER BY total_calls DESC'''
        )
        return [_row_to_dict(r) for r in rows]


# ── Credit configuration operations ──────────────────────────────────

def get_credit_config() -> dict:
    """Get all credit configuration as a dict."""
    with get_db() as conn:
        rows = _fetchall(conn, 'SELECT config_key, config_value FROM credit_config')
        result = {}
        for r in rows:
            d = _row_to_dict(r)
            if d:
                result[d['config_key']] = d['config_value']
        return result


def set_credit_config(key: str, value: str):
    """Update a credit configuration value."""
    with get_db() as conn:
        existing = _fetchone(conn,
            'SELECT id FROM credit_config WHERE config_key = ?', (key,))
        if existing:
            _execute(conn,
                "UPDATE credit_config SET config_value = ?, updated_at = datetime('now') WHERE config_key = ?",
                (value, key))
        else:
            _execute(conn,
                'INSERT INTO credit_config (config_key, config_value) VALUES (?, ?)',
                (key, value))


def get_credit_cost(api_name: str) -> float:
    """Get the credit cost for a given API call."""
    config = get_credit_config()
    cost_map = {
        'flux2pro': float(config.get('flux2pro_cost_per_image', '0.05')),
        'claude': float(config.get('claude_cost_per_call', '0.01')),
    }
    return cost_map.get(api_name, 0.0)


# ── Credit usage queries (admin) ─────────────────────────────────────

def get_total_credits_used() -> dict:
    """Get total credits used across all APIs."""
    with get_db() as conn:
        rows = _fetchall(conn,
            '''SELECT api_name,
                      COUNT(*) as total_calls,
                      SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                      SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures,
                      COALESCE(SUM(CASE WHEN success = 1 THEN credits_used ELSE 0 END), 0) as total_credits
               FROM api_logs
               GROUP BY api_name'''
        )
        result: dict = {}
        grand_total = 0.0
        for r in rows:
            d = _row_to_dict(r) or {}
            if d.get('api_name'):
                result[d['api_name']] = d
                grand_total += float(d.get('total_credits', 0))
        return {'by_api': result, 'grand_total': grand_total}


def get_credit_usage_history(days: int = 30) -> list:
    """Get daily credit usage history."""
    with get_db() as conn:
        rows = _fetchall(conn,
            '''SELECT DATE(created_at) as date,
                      api_name,
                      COUNT(*) as calls,
                      SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                      COALESCE(SUM(CASE WHEN success = 1 THEN credits_used ELSE 0 END), 0) as credits
               FROM api_logs
               WHERE created_at >= datetime('now', ?)
               GROUP BY DATE(created_at), api_name
               ORDER BY date DESC, api_name''',
            (f'-{days} days',)
        )
        return [_row_to_dict(r) for r in rows]


def get_credit_usage_by_user() -> list:
    """Get credit usage grouped by user (admin view)."""
    with get_db() as conn:
        rows = _fetchall(conn,
            '''SELECT al.user_id,
                      COALESCE(u.name, 'Anonymous') as user_name,
                      COALESCE(u.email, 'N/A') as email,
                      COUNT(*) as total_calls,
                      SUM(CASE WHEN al.success = 1 THEN 1 ELSE 0 END) as successes,
                      COALESCE(SUM(CASE WHEN al.success = 1 THEN al.credits_used ELSE 0 END), 0) as total_credits,
                      COUNT(DISTINCT DATE(al.created_at)) as active_days,
                      MAX(al.created_at) as last_activity
               FROM api_logs al
               LEFT JOIN users u ON al.user_id = u.id
               GROUP BY al.user_id
               ORDER BY total_credits DESC'''
        )
        return [_row_to_dict(r) for r in rows]


def get_hourly_usage_today() -> list:
    """Get hourly usage breakdown for today."""
    with get_db() as conn:
        rows = _fetchall(conn,
            '''SELECT strftime('%H', created_at) as hour,
                      api_name,
                      COUNT(*) as calls,
                      COALESCE(SUM(CASE WHEN success = 1 THEN credits_used ELSE 0 END), 0) as credits
               FROM api_logs
               WHERE DATE(created_at) = DATE('now')
               GROUP BY hour, api_name
               ORDER BY hour'''
        )
        return [_row_to_dict(r) for r in rows]


# ── Credit usage queries (per user) ──────────────────────────────────

def get_user_credit_usage(user_id: int) -> dict:
    """Get credit usage for a specific user."""
    with get_db() as conn:
        rows = _fetchall(conn,
            '''SELECT api_name,
                      COUNT(*) as total_calls,
                      SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                      SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures,
                      COALESCE(SUM(CASE WHEN success = 1 THEN credits_used ELSE 0 END), 0) as total_credits
               FROM api_logs
               WHERE user_id = ?
               GROUP BY api_name''',
            (user_id,)
        )
        result: dict = {}
        grand_total = 0.0
        for r in rows:
            d = _row_to_dict(r) or {}
            if d.get('api_name'):
                result[d['api_name']] = d
                grand_total += float(d.get('total_credits', 0))
        return {'by_api': result, 'grand_total': grand_total}


def get_user_credit_history(user_id: int, days: int = 30) -> list:
    """Get daily credit usage history for a specific user."""
    with get_db() as conn:
        rows = _fetchall(conn,
            '''SELECT DATE(created_at) as date,
                      api_name,
                      COUNT(*) as calls,
                      SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                      COALESCE(SUM(CASE WHEN success = 1 THEN credits_used ELSE 0 END), 0) as credits
               FROM api_logs
               WHERE user_id = ? AND created_at >= datetime('now', ?)
               GROUP BY DATE(created_at), api_name
               ORDER BY date DESC, api_name''',
            (user_id, f'-{days} days')
        )
        return [_row_to_dict(r) for r in rows]


def get_user_story_credits(user_id: int, limit: int = 20) -> list:
    """Get per-story credit breakdown for a user."""
    with get_db() as conn:
        rows = _fetchall(conn,
            '''SELECT s.id as story_id,
                      s.story_title,
                      s.child_name,
                      s.created_at,
                      COUNT(al.id) as api_calls,
                      COALESCE(SUM(CASE WHEN al.success = 1 THEN al.credits_used ELSE 0 END), 0) as credits_used
               FROM stories s
               LEFT JOIN api_logs al ON al.story_id = s.id
               WHERE s.user_id = ?
               GROUP BY s.id
               ORDER BY s.id DESC
               LIMIT ?''',
            (user_id, limit)
        )
        return [_row_to_dict(r) for r in rows]


# ── Admin operations ─────────────────────────────────────────────────

def is_user_admin(user_id: int) -> bool:
    """Check if a user has admin privileges."""
    with get_db() as conn:
        row = _fetchone(conn, 'SELECT is_admin FROM users WHERE id = ?', (user_id,))
        if row:
            d = _row_to_dict(row) or {}
            return bool(d.get('is_admin', 0))
        return False


def set_user_admin(user_id: int, is_admin: bool = True):
    """Set admin status for a user."""
    with get_db() as conn:
        _execute(conn, 'UPDATE users SET is_admin = ? WHERE id = ?',
                 (1 if is_admin else 0, user_id))


def get_all_users_summary() -> list:
    """Get summary of all users for admin view."""
    with get_db() as conn:
        rows = _fetchall(conn,
            '''SELECT u.id, u.name, u.email, u.is_admin, u.created_at, u.last_login,
                      COUNT(DISTINCT s.id) as story_count,
                      COALESCE(SUM(CASE WHEN al.success = 1 THEN al.credits_used ELSE 0 END), 0) as total_credits
               FROM users u
               LEFT JOIN stories s ON s.user_id = u.id
               LEFT JOIN api_logs al ON al.user_id = u.id
               GROUP BY u.id
               ORDER BY u.id DESC'''
        )
        return [_row_to_dict(r) for r in rows]


# ── User feedback operations ─────────────────────────────────────────

def submit_user_feedback(story_id: int = 0, user_id: Optional[int] = None,
                         star_rating: Optional[int] = None,
                         emoji_reaction: Optional[str] = None,
                         is_helpful: Optional[bool] = None,
                         comment: Optional[str] = None,
                         page_number: Optional[int] = None) -> Optional[dict]:
    """Submit user feedback for a story."""
    with get_db() as conn:
        helpful_val = None
        if is_helpful is not None:
            helpful_val = 1 if is_helpful else 0
        _execute(conn,
            '''INSERT INTO user_feedback
               (story_id, user_id, star_rating, emoji_reaction, is_helpful, comment, page_number)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (story_id, user_id, star_rating, emoji_reaction, helpful_val, comment, page_number)
        )
        rows = _fetchall(conn,
            'SELECT * FROM user_feedback WHERE story_id = ? ORDER BY id DESC LIMIT 1',
            (story_id,)
        )
        return _row_to_dict(rows[0]) if rows else None


def get_story_feedback_summary(story_id: int) -> dict:
    """Get aggregated feedback for a single story."""
    with get_db() as conn:
        row = _fetchone(conn,
            '''SELECT COUNT(*) as total_reviews,
                      AVG(star_rating) as avg_rating,
                      SUM(CASE WHEN is_helpful = 1 THEN 1 ELSE 0 END) as helpful_yes,
                      SUM(CASE WHEN is_helpful = 0 THEN 1 ELSE 0 END) as helpful_no
               FROM user_feedback WHERE story_id = ?''',
            (story_id,)
        )
        emoji_rows = _fetchall(conn,
            '''SELECT emoji_reaction, COUNT(*) as count
               FROM user_feedback WHERE story_id = ? AND emoji_reaction IS NOT NULL
               GROUP BY emoji_reaction ORDER BY count DESC''',
            (story_id,)
        )
        d = _row_to_dict(row) or {}
        d['emoji_counts'] = {_row_to_dict(r)['emoji_reaction']: _row_to_dict(r)['count']
                             for r in emoji_rows if _row_to_dict(r)}
        return d


def get_admin_feedback_stats() -> dict:
    """Get aggregated feedback stats for admin dashboard."""
    with get_db() as conn:
        overall = _fetchone(conn,
            '''SELECT COUNT(*) as total_reviews,
                      AVG(star_rating) as avg_rating,
                      SUM(CASE WHEN is_helpful = 1 THEN 1 ELSE 0 END) as helpful_yes,
                      SUM(CASE WHEN is_helpful = 0 THEN 1 ELSE 0 END) as helpful_no
               FROM user_feedback'''
        )
        by_condition = _fetchall(conn,
            '''SELECT s.condition,
                      COUNT(uf.id) as reviews,
                      AVG(uf.star_rating) as avg_rating
               FROM user_feedback uf
               JOIN stories s ON uf.story_id = s.id
               WHERE uf.star_rating IS NOT NULL
               GROUP BY s.condition
               ORDER BY avg_rating DESC'''
        )
        recent = _fetchall(conn,
            '''SELECT uf.*,
                      COALESCE(s.story_title, 'Overall Platform') as story_title,
                      COALESCE(s.condition, 'General') as condition
               FROM user_feedback uf
               LEFT JOIN stories s ON uf.story_id = s.id AND uf.story_id != 0
               ORDER BY uf.id DESC LIMIT 20'''
        )
        return {
            'overall': _row_to_dict(overall) or {},
            'by_condition': [_row_to_dict(r) for r in by_condition],
            'recent': [_row_to_dict(r) for r in recent],
        }
