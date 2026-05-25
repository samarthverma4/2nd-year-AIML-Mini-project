"""
Analytics Blueprint (Hospital tier only)
────────────────────────────────────────
Engagement metrics for the Hospital plan dashboard.

Returns a 30-day window of:
  - storybooks per child profile
  - most-used themes (by story title keywords / condition fallback)
  - stories per day (time-series for charts)
  - read-time totals via story_feedback
"""

import logging
from flask import Blueprint, jsonify, g

import database_v2 as db
from database_v2 import get_db, _fetchall
from auth import login_required
from subscription_decorators import require_tier

logger = logging.getLogger('brave_story.routes.analytics')

analytics_bp = Blueprint('analytics', __name__)


def _row_dict(r):
    return dict(r) if not isinstance(r, dict) else r


@analytics_bp.route('/api/analytics/engagement', methods=['GET'])
@login_required
@require_tier('hospital')
def engagement():
    """Aggregate 30-day engagement metrics scoped to the requesting user."""
    user_id = g.user_id
    with get_db() as conn:
        per_child = _fetchall(
            conn,
            '''SELECT child_name,
                      COUNT(*) AS stories,
                      MAX(created_at) AS last_story
               FROM stories
               WHERE user_id = ? AND created_at >= datetime('now', '-30 days')
               GROUP BY child_name
               ORDER BY stories DESC''',
            (user_id,),
        )
        by_condition = _fetchall(
            conn,
            '''SELECT COALESCE(NULLIF(condition, ''), 'Uncategorised') AS condition,
                      COUNT(*) AS stories
               FROM stories
               WHERE user_id = ? AND created_at >= datetime('now', '-30 days')
               GROUP BY condition
               ORDER BY stories DESC
               LIMIT 8''',
            (user_id,),
        )
        per_day = _fetchall(
            conn,
            '''SELECT DATE(created_at) AS day,
                      COUNT(*) AS stories
               FROM stories
               WHERE user_id = ? AND created_at >= datetime('now', '-30 days')
               GROUP BY day
               ORDER BY day''',
            (user_id,),
        )
        read_time = _fetchall(
            conn,
            '''SELECT s.child_name,
                      COALESCE(SUM(sf.total_read_time_sec), 0) AS read_seconds,
                      COALESCE(SUM(sf.read_count), 0) AS reads
               FROM stories s
               LEFT JOIN story_feedback sf ON sf.story_id = s.id
               WHERE s.user_id = ? AND s.created_at >= datetime('now', '-30 days')
               GROUP BY s.child_name
               ORDER BY read_seconds DESC''',
            (user_id,),
        )

    return jsonify({
        'window_days':   30,
        'per_child':     [_row_dict(r) for r in per_child],
        'by_condition':  [_row_dict(r) for r in by_condition],
        'per_day':       [_row_dict(r) for r in per_day],
        'read_time':     [_row_dict(r) for r in read_time],
    })
