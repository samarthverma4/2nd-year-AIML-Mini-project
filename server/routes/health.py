"""
Health & Admin Routes Blueprint
────────────────────────────────
Health-check endpoint, admin stats, and cloud storage management.
"""

import time
import logging
from flask import Blueprint, request, jsonify, g
from typing import Any

import database_v2 as db
from auth import login_required
from monitoring import usage_counter, perf_tracker
from functools import wraps


def admin_required(f):
    """Decorator: require admin privileges (stacks with @login_required)."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not db.is_user_admin(g.user_id):
            return jsonify({'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

logger = logging.getLogger('brave_story.routes.health')

health_bp = Blueprint('health', __name__)

# cloud storage injected at init time
_image_storage: Any = None


def init_health_bp(image_storage):
    """Inject the image storage backend for blob management routes."""
    global _image_storage
    _image_storage = image_storage


# ── Health check ─────────────────────────────────────────────────────

@health_bp.route('/api/health', methods=['GET'])
def health_check():
    """Return health status with uptime, memory, and Python version."""
    metrics = perf_tracker.get_metrics()
    return jsonify({
        'status': 'ok',
        'timestamp': int(time.time()),
        'uptime': metrics['uptime_human'],
        'uptime_seconds': metrics['uptime_seconds'],
        'memory_mb': metrics['memory_mb'],
        'python_version': metrics['python_version'],
    })


# ── Admin stats ──────────────────────────────────────────────────────

@health_bp.route('/api/admin/stats', methods=['GET'])
@admin_required
def get_stats():
    """Return aggregated API usage and performance statistics for admin."""
    return jsonify({
        'api_usage': db.get_api_usage_stats(),
        'today': usage_counter.get_today_stats(),
        'performance': perf_tracker.get_metrics(),
    })


# ── Storage info & blob management ───────────────────────────────────

@health_bp.route('/api/storage/info', methods=['GET'])
@admin_required
def storage_info():
    """Return current storage backend and configuration details."""
    from cloud_storage import STORAGE_BACKEND, AZURE_CONTAINER, AWS_BUCKET, AWS_REGION
    return jsonify({
        'backend': STORAGE_BACKEND,
        'details': {
            's3_bucket': AWS_BUCKET or None,
            's3_region': AWS_REGION or None,
            'azure_container': AZURE_CONTAINER or None,
        }
    })


@health_bp.route('/api/storage/blobs', methods=['GET'])
@admin_required
def list_blobs():
    """List all blobs/images in the Azure Blob container."""
    from cloud_storage import STORAGE_BACKEND, AZURE_CONN_STR, AZURE_CONTAINER
    if STORAGE_BACKEND != 'azure':
        return jsonify({'message': f'Storage backend is {STORAGE_BACKEND}, not azure'}), 400
    try:
        from azure.storage.blob import BlobServiceClient
        client = BlobServiceClient.from_connection_string(AZURE_CONN_STR)
        container = client.get_container_client(AZURE_CONTAINER)
        blobs = [
            {
                'name': b.name,
                'size': b.size,
                'created': b.creation_time.isoformat() if b.creation_time else None,
                'url': f'{client.url}{AZURE_CONTAINER}/{b.name}',
            }
            for b in container.list_blobs()
        ]
        return jsonify({'blobs': blobs, 'count': len(blobs)})
    except Exception as e:
        logger.error(f'Azure list blobs error: {e}')
        return jsonify({'message': str(e)}), 500


@health_bp.route('/api/storage/blobs/<path:filename>', methods=['GET'])
@admin_required
def get_blob_url(filename):
    """Get the public URL for a blob by filename."""
    from cloud_storage import STORAGE_BACKEND
    if STORAGE_BACKEND != 'azure':
        return jsonify({'message': f'Storage backend is {STORAGE_BACKEND}, not azure'}), 400
    try:
        url = _image_storage.get_url(filename)
        return jsonify({'filename': filename, 'url': url})
    except Exception as e:
        logger.error(f'Azure get blob URL error: {e}')
        return jsonify({'message': str(e)}), 500


@health_bp.route('/api/storage/blobs/<path:filename>', methods=['DELETE'])
@admin_required
def delete_blob(filename):
    """Delete a blob from Azure Blob storage."""
    from cloud_storage import STORAGE_BACKEND
    if STORAGE_BACKEND != 'azure':
        return jsonify({'message': f'Storage backend is {STORAGE_BACKEND}, not azure'}), 400
    try:
        success = _image_storage.delete_image(filename)
        if not success:
            return jsonify({'message': 'Blob not found or already deleted'}), 404
        logger.info(f'Blob deleted: {filename}')
        return jsonify({'success': True, 'deleted': filename})
    except Exception as e:
        logger.error(f'Azure delete blob error: {e}')
        return jsonify({'message': str(e)}), 500


@health_bp.route('/api/storage/blobs/upload', methods=['POST'])
@admin_required
def upload_blob():
    """Upload an image file directly to Azure Blob storage."""
    from cloud_storage import STORAGE_BACKEND
    if STORAGE_BACKEND != 'azure':
        return jsonify({'message': f'Storage backend is {STORAGE_BACKEND}, not azure'}), 400
    if 'file' not in request.files:
        return jsonify({'message': 'No file provided'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'message': 'Empty filename'}), 400
    try:
        filename = f'upload_{int(time.time())}_{file.filename}'
        url = _image_storage.save_image(file.read(), filename)
        logger.info(f'Blob uploaded: {filename}')
        return jsonify({'success': True, 'filename': filename, 'url': url}), 201
    except Exception as e:
        logger.error(f'Azure upload error: {e}')
        return jsonify({'message': str(e)}), 500
