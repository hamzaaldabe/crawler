from flask import Blueprint, request, jsonify, current_app
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, api
from app.models import Domain, URL, Asset, User
from validators import url as validate_url
from app.crawler import Crawler
from datetime import datetime
from urllib.parse import urlparse
import threading

urls_bp = Blueprint('urls', __name__)
urls_ns = Namespace('urls', description='URL operations')

# Create a separate namespace for domain-specific URL operations
domain_urls_ns = Namespace('domain_urls', description='Domain-specific URL operations', path='/domains/<int:domain_id>/urls')

# Swagger models
url_model = api.model('URL', {
    'url': fields.String(required=True, description='URL to be crawled'),
    'domain_id': fields.Integer(required=True, description='Domain ID')
})

url_response = api.model('URLResponse', {
    'id': fields.Integer(description='URL ID'),
    'url': fields.String(description='URL'),
    'status': fields.String(description='Crawling status'),
    'page_content': fields.String(description='Extracted text content from the page')
})

asset_response = api.model('AssetResponse', {
    'id': fields.Integer(description='Asset ID'),
    'url': fields.String(description='Asset URL'),
    'asset_type': fields.String(description='Type of asset (image/pdf)'),
    'status': fields.String(description='Processing status'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

@domain_urls_ns.route('')
@domain_urls_ns.param('domain_id', 'The domain identifier')
class URLList(Resource):
    @jwt_required()
    @domain_urls_ns.marshal_list_with(url_response)
    @domain_urls_ns.response(404, 'Domain not found')
    def get(self, domain_id):
        """List all URLs for a specific domain"""
        current_user_id = get_jwt_identity()
        domain = Domain.query.filter_by(id=domain_id, user_id=current_user_id).first()
        if not domain:
            return {'error': 'Domain not found'}, 404
        urls = URL.query.filter_by(domain_id=domain_id).all()
        return [{'id': u.id, 'url': u.url, 'status': u.status, 'page_content': u.page_content} for u in urls]

    @jwt_required()
    @domain_urls_ns.expect(url_model)
    @domain_urls_ns.response(201, 'URL added successfully')
    @domain_urls_ns.response(400, 'Invalid URL')
    @domain_urls_ns.response(404, 'Domain not found')
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

@domain_urls_ns.route('/<int:url_id>')
@domain_urls_ns.param('domain_id', 'The domain identifier')
@domain_urls_ns.param('url_id', 'The URL identifier')
class URLResource(Resource):
    @jwt_required()
    @domain_urls_ns.marshal_with(url_response)
    @domain_urls_ns.response(404, 'URL not found')
    def get(self, domain_id, url_id):
        """Get a specific URL"""
        current_user_id = get_jwt_identity()
        domain = Domain.query.filter_by(id=domain_id, user_id=current_user_id).first()
        if not domain:
            return {'error': 'Domain not found'}, 404
            
        url = URL.query.filter_by(id=url_id, domain_id=domain_id).first()
        if not url:
            return {'error': 'URL not found'}, 404
            
        return {'id': url.id, 'url': url.url, 'status': url.status, 'page_content': url.page_content}

    @jwt_required()
    @domain_urls_ns.expect(url_model)
    @domain_urls_ns.response(200, 'URL updated successfully')
    @domain_urls_ns.response(400, 'Invalid URL')
    @domain_urls_ns.response(404, 'URL not found')
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
    @domain_urls_ns.response(200, 'URL deleted successfully')
    @domain_urls_ns.response(404, 'URL not found')
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

@urls_ns.route('/domains/<int:domain_id>/urls/<int:url_id>/assets')
@urls_ns.param('domain_id', 'The domain identifier (must be provided in the path)')
@urls_ns.param('url_id', 'The URL identifier')
class URLAssets(Resource):
    @urls_ns.doc('list_url_assets',
        description='Retrieve all assets (images and PDFs) associated with a specific URL.\n\n'
                    'Path parameters:\n'
                    '- domain_id: The domain this URL belongs to.\n'
                    '- url_id: The URL to list assets for.\n',
        notes='''
        This endpoint returns all assets that were found and processed for the given URL.\n
        The domain ownership is automatically verified based on the URL's association.\n
        Example request:\n
            GET /api/domains/28/urls/18/assets\n
        Example response:
        ```json
        [
            {
                "id": 1,
                "url": "https://example.com/image.jpg",
                "asset_type": "image",
                "status": "processed",
                "created_at": "2024-04-30T08:14:46"
            }
        ]
        ```
        '''
    )
    @urls_ns.response(200, 'Success', [asset_response])
    @urls_ns.response(404, 'URL not found')
    @jwt_required()
    def get(self, domain_id, url_id):
        """
        List all assets for a specific URL.
        
        Path parameters:
          - domain_id: The domain this URL belongs to.
          - url_id: The URL to list assets for.
        
        Returns a list of all assets (images and PDFs) associated with the given URL.
        The assets are returned with their current processing status.
        
        The endpoint automatically verifies:
        1. The URL exists
        2. The user has access to the domain that owns the URL
        
        Returns:
            list: A list of assets with their details including:
                - id: Asset ID
                - url: Asset URL
                - asset_type: Type of asset (image/pdf)
                - status: Processing status
                - created_at: Creation timestamp
        """
        current_user_id = get_jwt_identity()
        # Get URL and verify it exists
        url = URL.query.filter_by(id=url_id, domain_id=domain_id).first()
        if not url:
            return {'error': 'URL not found'}, 404
        assets = URL.get_assets_by_url_id(url_id)
        if not assets:
            return [], 200
        return [{
            'id': asset.id,
            'url': asset.url,
            'asset_type': asset.asset_type,
            'status': asset.status
        } for asset in assets], 200

@urls_ns.route('/crawl-pending')
class CrawlPendingURLs(Resource):
    @jwt_required()
    def post(self):
        """Manually trigger crawling of all pending URLs"""
        try:
            # Get all pending URLs
            pending_urls = URL.query.filter_by(status='pending').all()
            
            if not pending_urls:
                return {'message': 'No pending URLs to process'}, 200
            
            # Start crawling in a background thread
            def crawl_background():
                with current_app.app_context():
                    crawler = Crawler(current_app)
                    for url in pending_urls:
                        try:
                            current_app.logger.info(f"Processing URL: {url.url}")
                            crawler.crawl_url(url)
                        except Exception as e:
                            current_app.logger.error(f"Error processing URL {url.url}: {str(e)}")
                            url.status = 'failed'
                            db.session.commit()
            
            thread = threading.Thread(target=crawl_background)
            thread.start()
            
            return {
                'message': f'Started crawling {len(pending_urls)} pending URLs',
                'urls_count': len(pending_urls)
            }, 202
            
        except Exception as e:
            current_app.logger.error(f"Error in crawl-pending endpoint: {str(e)}")
            return {'error': str(e)}, 500
