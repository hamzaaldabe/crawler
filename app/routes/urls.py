from flask import Blueprint, request, jsonify
from app import db, auth
from app.models import Domain, URL
from validators import url as validate_url

urls_bp = Blueprint('urls', __name__, url_prefix='/domains/<int:domain_id>/urls')

@urls_bp.route('', methods=['POST'])
@auth.login_required
def add_url(domain_id):
    data = request.get_json() or {}
    url_str = data.get('url')
    if not url_str or not validate_url(url_str):
        return jsonify({'error': 'Invalid or missing URL'}), 400
    domain = Domain.query.filter_by(id=domain_id, user_id=auth.current_user().id).first()
    if not domain:
        return jsonify({'error': 'Domain not found'}), 404
    url_entry = URL(url=url_str, domain=domain)
    db.session.add(url_entry)
    db.session.commit()
    return jsonify({'message': 'URL added successfully', 'url_id': url_entry.id}), 201

@urls_bp.route('', methods=['GET'])
@auth.login_required
def list_urls(domain_id):
    domain = Domain.query.filter_by(id=domain_id, user_id=auth.current_user().id).first()
    if not domain:
        return jsonify({'error': 'Domain not found'}), 404
    urls = URL.query.filter_by(domain_id=domain_id).all()
    return jsonify([{'id': u.id, 'url': u.url, 'status': u.status} for u in urls])
