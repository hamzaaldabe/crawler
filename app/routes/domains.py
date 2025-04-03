from flask import Blueprint, request, jsonify
from app import db, auth
from app.models import Domain
from validators import domain as validate_domain

domains_bp = Blueprint('domains', __name__, url_prefix='/domains')

@domains_bp.route('', methods=['POST'])
@auth.login_required
def add_domain():
    data = request.get_json() or {}
    domain_name = data.get('domain')
    if not domain_name or not validate_domain(domain_name):
        return jsonify({'error': 'Invalid or missing domain'}), 400
    domain = Domain(domain=domain_name, owner=auth.current_user())
    db.session.add(domain)
    db.session.commit()
    return jsonify({'message': 'Domain added successfully', 'domain_id': domain.id}), 201

@domains_bp.route('', methods=['GET'])
@auth.login_required
def list_domains():
    domains = Domain.query.filter_by(user_id=auth.current_user().id).all()
    return jsonify([{'id': d.id, 'domain': d.domain} for d in domains])
