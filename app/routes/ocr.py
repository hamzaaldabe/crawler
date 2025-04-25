from flask import Blueprint, request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import Asset, OCRResult, URL, Domain
from app.ocr import OCRProcessor

ocr_bp = Blueprint('ocr', __name__)
ocr_ns = Namespace('ocr', description='OCR operations')

# Swagger models
ocr_response = ocr_ns.model('OCRResponse', {
    'message': fields.String(description='Operation result message'),
    'asset_id': fields.Integer(description='ID of the processed asset'),
    'ocr_result': fields.Nested(ocr_ns.model('OCRResult', {
        'id': fields.Integer(description='OCR result ID'),
        'content': fields.String(description='Extracted text content'),
        'confidence': fields.Float(description='OCR confidence score')
    }))
})

@ocr_ns.route('/assets/<int:asset_id>/process')
class ProcessAssetOCR(Resource):
    @ocr_ns.doc('process_asset_ocr',
                description='Trigger OCR processing for a specific asset',
                security='Bearer Auth')
    @ocr_ns.response(200, 'Success', ocr_response)
    @ocr_ns.response(404, 'Asset not found')
    @ocr_ns.response(403, 'Access denied')
    @jwt_required()
    def post(self, asset_id):
        """Trigger OCR processing for a specific asset"""
        # Get current user
        current_user_id = get_jwt_identity()
        
        # Get asset and verify ownership
        asset = Asset.query.get_or_404(asset_id)
        url = URL.query.get_or_404(asset.url_id)
        domain = Domain.query.get_or_404(url.domain_id)
        # if domain.user_id != current_user_id:
        #     return {'message': 'Access denied'}, 403
            
        # Initialize OCR processor
        ocr_processor = OCRProcessor()
        
        # Process based on asset type
        if asset.asset_type == 'image':
            result = ocr_processor.process_image(asset.url, asset.id)
        elif asset.asset_type == 'pdf':
            result = ocr_processor.process_pdf(asset.url, asset.id)
        else:
            return {'message': 'Unsupported asset type'}, 400
            
        if result:
            return {
                'message': 'OCR processing completed successfully',
                'asset_id': asset.id,
                'ocr_result': {
                    'id': result.id,
                    'content': result.content,
                    'confidence': result.confidence
                }
            }, 200
        else:
            return {'message': 'OCR processing failed'}, 500

@ocr_ns.route('/assets/<int:asset_id>/results')
class GetAssetOCRResults(Resource):
    @ocr_ns.doc('get_asset_ocr_results',
                description='Get OCR results for a specific asset',
                security='Bearer Auth')
    @ocr_ns.response(200, 'Success', ocr_response)
    @ocr_ns.response(404, 'Asset not found')
    @ocr_ns.response(403, 'Access denied')
    @jwt_required()
    def get(self, asset_id):
        """Get OCR results for a specific asset"""
        # Get current user
        current_user_id = get_jwt_identity()
        
        # Get asset and verify ownership
        asset = Asset.query.get_or_404(asset_id)
        url = URL.query.get_or_404(asset.url_id)
        
        if url.user_id != current_user_id:
            return {'message': 'Access denied'}, 403
            
        # Get OCR results
        ocr_result = OCRResult.query.filter_by(asset_id=asset.id).first()
        
        if ocr_result:
            return {
                'message': 'OCR results retrieved successfully',
                'asset_id': asset.id,
                'ocr_result': {
                    'id': ocr_result.id,
                    'content': ocr_result.content,
                    'confidence': ocr_result.confidence
                }
            }, 200
        else:
            return {'message': 'No OCR results found'}, 404 