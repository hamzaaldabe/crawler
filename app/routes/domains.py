from flask import Blueprint, request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, api
from app.models import Domain, URL
from validators import domain as validate_domain
from validators import url as validate_url
import io
import logging

# Set up logging
logger = logging.getLogger(__name__)

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

bulk_import_response = api.model('BulkImportResponse', {
    'message': fields.String(description='Import status message'),
    'total_urls': fields.Integer(description='Total URLs in file'),
    'successful_imports': fields.Integer(description='Number of successfully imported URLs'),
    'failed_imports': fields.Integer(description='Number of failed imports'),
    'failed_urls': fields.List(fields.String, description='List of URLs that failed to import')
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

@domains_ns.route('/<int:domain_id>/bulk-import')
@domains_ns.param('domain_id', 'The domain identifier')
class BulkImportURLs(Resource):
    @jwt_required()
    @domains_ns.doc('bulk_import_urls',
        description='Bulk import URLs from a text file to a specific domain.\n\n'
                    'This endpoint allows you to upload a text file containing multiple URLs '
                    'and import them all at once to a domain. Each URL should be on a separate line.\n\n'
                    '**Features:**\n'
                    '- Validates each URL format\n'
                    '- Skips duplicate URLs\n'
                    '- Provides detailed import results\n'
                    '- Supports UTF-8 encoded text files\n\n'
                    '**File Format:**\n'
                    'Upload a plain text file (.txt) with one URL per line:\n'
                    '```\n'
                    'https://example.com/page1\n'
                    'https://example.com/page2\n'
                    'https://example.com/page3\n'
                    '```\n\n'
                    '**Response includes:**\n'
                    '- Total URLs processed\n'
                    '- Number of successful imports\n'
                    '- Number of failed imports\n'
                    '- List of failed URLs with reasons',
        notes='''
        **Example Usage:**
        
        ```bash
        curl -X POST "http://localhost:5000/api/domains/4/bulk-import" \\
             -H "Authorization: Bearer YOUR_JWT_TOKEN" \\
             -F "file=@urls.txt"
        ```
        
        **Example Response:**
        ```json
        {
            "message": "Bulk import completed",
            "total_urls": 5,
            "successful_imports": 4,
            "failed_imports": 1,
            "failed_urls": [
                "https://example.com/page1 (already exists)"
            ]
        }
        ```
        
        **Error Cases:**
        - Invalid URL format: URL will be skipped and reported
        - Duplicate URL: URL will be skipped and reported
        - File format issues: Request will fail with error message
        - Domain not found: 404 error
        - Unauthorized access: 401 error
        ''',
        security='Bearer Auth'
    )
    @domains_ns.expect(api.parser().add_argument('file', location='files', type='FileStorage', required=True, help='Text file containing URLs (one per line)'))
    @domains_ns.marshal_with(bulk_import_response)
    @domains_ns.response(200, 'Bulk import completed successfully', bulk_import_response)
    @domains_ns.response(400, 'Invalid file or domain')
    @domains_ns.response(401, 'Unauthorized')
    @domains_ns.response(404, 'Domain not found')
    def post(self, domain_id):
        """Bulk import URLs from a text file to a domain"""
        current_user_id = get_jwt_identity()
        
        logger.info(f"Bulk import request received for domain_id: {domain_id}, user_id: {current_user_id}")
        
        # Verify domain exists and user has access
        domain = Domain.query.filter_by(id=domain_id, user_id=current_user_id).first()
        if not domain:
            logger.error(f"Domain not found: domain_id={domain_id}, user_id={current_user_id}")
            return {'error': 'Domain not found'}, 404
        
        logger.info(f"Domain found: {domain.domain}")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            logger.error("No file in request.files")
            logger.info(f"Available keys in request.files: {list(request.files.keys())}")
            return {'error': 'No file provided'}, 400
        
        file = request.files['file']
        logger.info(f"File received: {file.filename}, size: {len(file.read()) if file else 'N/A'}")
        
        # Reset file pointer after reading
        file.seek(0)
        
        if file.filename == '':
            logger.error("Empty filename")
            return {'error': 'No file selected'}, 400
        
        # Read and process the file
        try:
            # Read file content
            content = file.read().decode('utf-8')
            logger.info(f"File content length: {len(content)} characters")
            logger.info(f"File content preview: {content[:200]}...")
            
            urls = [line.strip() for line in content.split('\n') if line.strip()]
            logger.info(f"Extracted {len(urls)} URLs from file")
            logger.info(f"URLs: {urls}")
            
            successful_imports = 0
            failed_imports = 0
            failed_urls = []
            
            for url in urls:
                try:
                    logger.info(f"Processing URL: {url}")
                    
                    # Validate URL
                    if not validate_url(url):
                        logger.warning(f"Invalid URL format: {url}")
                        failed_imports += 1
                        failed_urls.append(f"{url} (invalid format)")
                        continue
                    
                    # Check if URL already exists for this domain
                    existing_url = URL.query.filter_by(url=url, domain_id=domain_id).first()
                    if existing_url:
                        logger.info(f"URL already exists: {url}")
                        failed_imports += 1
                        failed_urls.append(f"{url} (already exists)")
                        continue
                    
                    # Create new URL
                    url_entry = URL(url=url, domain=domain, status='pending')
                    db.session.add(url_entry)
                    successful_imports += 1
                    logger.info(f"Successfully added URL: {url}")
                    
                except Exception as e:
                    logger.error(f"Error processing URL {url}: {str(e)}")
                    failed_imports += 1
                    failed_urls.append(f"{url} (error: {str(e)})")
            
            # Commit all successful imports
            db.session.commit()
            logger.info(f"Bulk import completed. Successful: {successful_imports}, Failed: {failed_imports}")
            
            return {
                'message': 'Bulk import completed',
                'total_urls': len(urls),
                'successful_imports': successful_imports,
                'failed_imports': failed_imports,
                'failed_urls': failed_urls
            }, 200
            
        except Exception as e:
            logger.error(f"Error in bulk import: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            db.session.rollback()
            return {'error': f'Error processing file: {str(e)}'}, 400
