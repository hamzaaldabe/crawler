from flask import Blueprint, request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, api
from app.models import Domain
from validators import domain as validate_domain

domains_bp = Blueprint('domains', __name__)
domains_ns = Namespace('domains', description='Domain operations', path='/domains')

# Swagger models
domain_model = api.model('Domain', {
    'domain': fields.String(required=True, description='Domain name')
})

domain_response = api.model('DomainResponse', {
    'id': fields.Integer(description='Domain ID'),
    'domain': fields.String(description='Domain name')
})

@domains_ns.route('')
class DomainList(Resource):
    @jwt_required()
    @domains_ns.marshal_list_with(domain_response)
    def get(self):
        """List all domains for the current user"""
        current_user_id = get_jwt_identity()
        domains = Domain.query.filter_by(user_id=current_user_id).all()
        return [{'id': d.id, 'domain': d.domain} for d in domains]

    @jwt_required()
    @domains_ns.expect(domain_model)
    @domains_ns.response(201, 'Domain added successfully', domain_response)
    @domains_ns.response(400, 'Invalid domain')
    def post(self):
        """Add a new domain"""
        current_user_id = get_jwt_identity()
        data = request.get_json() or {}
        domain_name = data.get('domain')
        if not domain_name or not validate_domain(domain_name):
            return {'error': 'Invalid or missing domain'}, 400
        domain = Domain(domain=domain_name, user_id=current_user_id)
        db.session.add(domain)
        db.session.commit()
        return {'id': domain.id, 'domain': domain.domain}, 201

@domains_ns.route('/<int:domain_id>')
@domains_ns.param('domain_id', 'The domain identifier')
class DomainResource(Resource):
    @jwt_required()
    @domains_ns.marshal_with(domain_response)
    @domains_ns.response(404, 'Domain not found')
    def get(self, domain_id):
        """Get a specific domain"""
        current_user_id = get_jwt_identity()
        domain = Domain.query.filter_by(id=domain_id, user_id=current_user_id).first()
        if not domain:
            return {'error': 'Domain not found'}, 404
        return {'id': domain.id, 'domain': domain.domain}

    @jwt_required()
    @domains_ns.expect(domain_model)
    @domains_ns.response(200, 'Domain updated successfully', domain_response)
    @domains_ns.response(400, 'Invalid domain')
    @domains_ns.response(404, 'Domain not found')
    def put(self, domain_id):
        """Update a domain"""
        current_user_id = get_jwt_identity()
        domain = Domain.query.filter_by(id=domain_id, user_id=current_user_id).first()
        if not domain:
            return {'error': 'Domain not found'}, 404

        data = request.get_json() or {}
        domain_name = data.get('domain')
        if not domain_name or not validate_domain(domain_name):
            return {'error': 'Invalid or missing domain'}, 400

        domain.domain = domain_name
        db.session.commit()
        return {'id': domain.id, 'domain': domain.domain}, 200

    @jwt_required()
    @domains_ns.response(200, 'Domain deleted successfully')
    @domains_ns.response(404, 'Domain not found')
    def delete(self, domain_id):
        """Delete a domain"""
        current_user_id = get_jwt_identity()
        domain = Domain.query.filter_by(id=domain_id, user_id=current_user_id).first()
        if not domain:
            return {'error': 'Domain not found'}, 404

        db.session.delete(domain)
        db.session.commit()
        return {'message': 'Domain deleted successfully'}, 200
