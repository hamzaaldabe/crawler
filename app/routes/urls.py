from flask import Blueprint, request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, api
from app.models import Domain, URL
from validators import url as validate_url

urls_bp = Blueprint('urls', __name__)
urls_ns = Namespace('urls', description='URL operations', path='/domains/<int:domain_id>/urls')

# Swagger models
url_model = api.model('URL', {
    'url': fields.String(required=True, description='URL to be crawled')
})

url_response = api.model('URLResponse', {
    'id': fields.Integer(description='URL ID'),
    'url': fields.String(description='URL'),
    'status': fields.String(description='Crawling status')
})

@urls_ns.route('')
@urls_ns.param('domain_id', 'The domain identifier')
class URLList(Resource):
    @jwt_required()
    @urls_ns.marshal_list_with(url_response)
    @urls_ns.response(404, 'Domain not found')
    def get(self, domain_id):
        """List all URLs for a specific domain"""
        current_user_id = get_jwt_identity()
        domain = Domain.query.filter_by(id=domain_id, user_id=current_user_id).first()
        if not domain:
            return {'error': 'Domain not found'}, 404
        urls = URL.query.filter_by(domain_id=domain_id).all()
        return [{'id': u.id, 'url': u.url, 'status': u.status} for u in urls]

    @jwt_required()
    @urls_ns.expect(url_model)
    @urls_ns.response(201, 'URL added successfully')
    @urls_ns.response(400, 'Invalid URL')
    @urls_ns.response(404, 'Domain not found')
    def post(self, domain_id):
        """Add a new URL to a domain"""
        current_user_id = get_jwt_identity()
        data = request.get_json() or {}
        url_str = data.get('url')
        if not url_str or not validate_url(url_str):
            return {'error': 'Invalid or missing URL'}, 400
        domain = Domain.query.filter_by(id=domain_id, user_id=current_user_id).first()
        if not domain:
            return {'error': 'Domain not found'}, 404
        url_entry = URL(url=url_str, domain=domain)
        db.session.add(url_entry)
        db.session.commit()
        return {'message': 'URL added successfully', 'url_id': url_entry.id}, 201

@urls_ns.route('/<int:url_id>')
@urls_ns.param('domain_id', 'The domain identifier')
@urls_ns.param('url_id', 'The URL identifier')
class URLResource(Resource):
    @jwt_required()
    @urls_ns.marshal_with(url_response)
    @urls_ns.response(404, 'URL not found')
    def get(self, domain_id, url_id):
        """Get a specific URL"""
        current_user_id = get_jwt_identity()
        domain = Domain.query.filter_by(id=domain_id, user_id=current_user_id).first()
        if not domain:
            return {'error': 'Domain not found'}, 404
            
        url = URL.query.filter_by(id=url_id, domain_id=domain_id).first()
        if not url:
            return {'error': 'URL not found'}, 404
            
        return {'id': url.id, 'url': url.url, 'status': url.status}

    @jwt_required()
    @urls_ns.expect(url_model)
    @urls_ns.response(200, 'URL updated successfully')
    @urls_ns.response(400, 'Invalid URL')
    @urls_ns.response(404, 'URL not found')
    def put(self, domain_id, url_id):
        """Update a URL"""
        current_user_id = get_jwt_identity()
        domain = Domain.query.filter_by(id=domain_id, user_id=current_user_id).first()
        if not domain:
            return {'error': 'Domain not found'}, 404
            
        url = URL.query.filter_by(id=url_id, domain_id=domain_id).first()
        if not url:
            return {'error': 'URL not found'}, 404

        data = request.get_json() or {}
        url_str = data.get('url')
        if not url_str or not validate_url(url_str):
            return {'error': 'Invalid or missing URL'}, 400

        url.url = url_str
        db.session.commit()
        return {'message': 'URL updated successfully'}, 200

    @jwt_required()
    @urls_ns.response(200, 'URL deleted successfully')
    @urls_ns.response(404, 'URL not found')
    def delete(self, domain_id, url_id):
        """Delete a URL"""
        current_user_id = get_jwt_identity()
        domain = Domain.query.filter_by(id=domain_id, user_id=current_user_id).first()
        if not domain:
            return {'error': 'Domain not found'}, 404
            
        url = URL.query.filter_by(id=url_id, domain_id=domain_id).first()
        if not url:
            return {'error': 'URL not found'}, 404

        db.session.delete(url)
        db.session.commit()
        return {'message': 'URL deleted successfully'}, 200
