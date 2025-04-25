from flask import Blueprint, request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, api
from app.models import Asset, URL, Domain, User

assets_bp = Blueprint('assets', __name__)
assets_ns = Namespace('assets', description='Asset operations', path='/assets')

# Swagger models
ocr_result_response = api.model('OCRResultResponse', {
    'id': fields.Integer(description='OCR Result ID'),
    'content': fields.String(description='Extracted text content'),
    'confidence': fields.Float(description='Confidence score of OCR'),
    'created_at': fields.DateTime(description='Creation timestamp')
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