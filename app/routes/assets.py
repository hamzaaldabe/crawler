from flask import Blueprint, request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, api
from app.models import Asset, URL, Domain, User
from validators import url as validate_url
import os

assets_bp = Blueprint('assets', __name__)
assets_ns = Namespace('assets', description='Asset operations', path='/assets')

# Swagger models
ocr_result_response = api.model('OCRResultResponse', {
    'id': fields.Integer(description='OCR Result ID'),
    'content': fields.String(description='Extracted text content'),
    'confidence': fields.Float(description='Confidence score of OCR'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

asset_input_model = api.model('AssetInput', {
    'asset_url': fields.String(required=True, description='URL of the asset (image or PDF)'),
    'parent_url_id': fields.Integer(required=True, description='The ID of the URL this asset belongs to')
})

asset_response_model = api.model('AssetResponse', {
    'id': fields.Integer(description='Asset ID'),
    'url': fields.String(description='Asset URL'),
    'asset_type': fields.String(description='Type of asset (image/pdf)'),
    'status': fields.String(description='Processing status'),
    'parent_url_id': fields.Integer(description='The ID of the URL this asset belongs to')
})

@assets_ns.route('/<int:asset_id>/ocr-results')
class AssetOCRResults(Resource):
    @assets_ns.doc('list_asset_ocr_results')
    @assets_ns.response(200, 'Success', [ocr_result_response])
    @assets_ns.response(404, 'Asset not found')
    @jwt_required()
    def get(self, asset_id):
        """
        List all OCR results for a specific asset
        
        Returns a list of OCR results for the given asset, including the extracted
        text content and confidence scores.
        """
        current_user_id = get_jwt_identity()
        asset = Asset.query.get_or_404(asset_id)
        
        # Verify user has access to this asset's URL's domain
        url = URL.query.get(asset.url_id)
        domain = Domain.query.get(url.domain_id)
        if domain.user_id != current_user_id:
            return {'error': 'Unauthorized access to asset'}, 403
        
        results = Asset.get_ocr_results_by_asset_id(asset_id)
        if not results:
            return [], 200
            
        return [{
            'id': result.id,
            'content': result.content,
            'confidence': result.confidence,
            'created_at': result.created_at.isoformat() if result.created_at else None
        } for result in results], 200

@assets_ns.route('')
class AssetResource(Resource):
    @jwt_required()
    @assets_ns.expect(asset_input_model)
    @assets_ns.marshal_with(asset_response_model, code=201)
    @assets_ns.response(400, 'Invalid input')
    @assets_ns.response(403, 'Forbidden')
    @assets_ns.response(404, 'Parent URL not found')
    def post(self):
        """Add a new asset (image or PDF) from a URL."""
        current_user_id = get_jwt_identity()
        data = request.get_json()

        asset_url = data.get('asset_url')
        parent_url_id = data.get('parent_url_id')

        if not asset_url or not validate_url(asset_url):
            return {'message': 'Invalid or missing asset URL'}, 400

        parent_url = URL.query.join(URL.domain).filter(URL.id == parent_url_id, Domain.user_id == current_user_id).first()

        if not parent_url:
            return {'message': 'Parent URL not found or you do not have permission to access it.'}, 404

        # Determine asset type from URL
        file_extension = os.path.splitext(asset_url)[1].lower()
        if file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
            asset_type = 'image'
        elif file_extension == '.pdf':
            asset_type = 'pdf'
        else:
            return {'message': 'Unsupported asset type. Only images and PDFs are allowed.'}, 400

        new_asset = Asset(
            url=asset_url,
            asset_type=asset_type,
            url_id=parent_url_id,
            status='pending'
        )

        db.session.add(new_asset)
        db.session.commit()

        return new_asset, 201 