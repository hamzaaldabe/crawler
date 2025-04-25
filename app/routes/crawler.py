from flask import Blueprint, request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, api
from app.models import URL, Domain
from app.crawler import Crawler

crawler_bp = Blueprint('crawler', __name__)
crawler_ns = Namespace('crawler', description='Crawler operations', path='/crawler')

# Swagger models
crawl_response = api.model('CrawlResponse', {
    'message': fields.String(description='Crawling status message'),
    'urls_processed': fields.Integer(description='Number of URLs processed'),
    'total_assets_found': fields.Integer(description='Total number of assets found')
})

@crawler_ns.route('/crawl-pending')
class CrawlPending(Resource):
    @crawler_ns.doc('crawl_pending')
    @crawler_ns.response(200, 'Crawling completed successfully', crawl_response)
    @jwt_required()
    def post(self):
        """
        Manually trigger crawling for all pending URLs
        
        This endpoint will crawl all URLs with 'pending' status,
        processing any images and PDFs found on the pages.
        """
        current_user_id = get_jwt_identity()
        
        # Get all pending URLs for the current user
        pending_urls = URL.query.join(Domain).filter(
            URL.status == 'pending',
            Domain.user_id == current_user_id
        ).all()
        
        if not pending_urls:
            return {
                'message': 'No pending URLs found',
                'urls_processed': 0,
                'total_assets_found': 0
            }, 200
            
        # Initialize crawler with app context
        crawler = Crawler()
        total_assets = 0
        
        # Process each URL
        for url in pending_urls:
            crawler.crawl_url(url)
            total_assets += len(url.assets)
        
        return {
            'message': 'Crawling completed successfully',
            'urls_processed': len(pending_urls),
            'total_assets_found': total_assets
        }, 200 