from google.cloud import vision
from google.cloud import storage
from google.api_core import retry
from google.api_core.exceptions import GoogleAPIError
import requests
from io import BytesIO
from PIL import Image
import os
import logging
from app import db
from app.models import OCRResult, Asset
from flask import current_app
import tempfile
import json

class OCRProcessor:
    def __init__(self):
        try:
            # Initialize logging
            self.logger = logging.getLogger(__name__)
            
            # Get credentials path from config
            credentials_path = current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS')
            if not credentials_path or not os.path.exists(credentials_path):
                raise ValueError("Google Cloud credentials file not found or not configured")
            
            # Initialize clients with explicit credentials
            self.client = vision.ImageAnnotatorClient.from_service_account_json(credentials_path)
            self.storage_client = storage.Client.from_service_account_json(credentials_path)
            
            # Get bucket name from config
            self.bucket_name = current_app.config.get('GCS_BUCKET_NAME')
            if not self.bucket_name:
                raise ValueError("GCS_BUCKET_NAME is not configured")
            
            # Verify bucket exists and is accessible
            try:
                self.storage_client.get_bucket(self.bucket_name)
            except Exception as e:
                raise ValueError(f"Failed to access bucket {self.bucket_name}: {str(e)}")
                
            self.logger.info("OCR Processor initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Error initializing OCR processor: {str(e)}")
            raise

    def set_asset_status(self, asset_id, status):
        """Helper to update asset status."""
        try:
            asset = Asset.query.get(asset_id)
            if asset:
                asset.status = status
                db.session.commit()
        except Exception as e:
            self.logger.error(f"Error updating status for asset {asset_id}: {e}")
            db.session.rollback()

    @retry.Retry(
        predicate=retry.if_exception_type(GoogleAPIError),
        initial=1.0,
        maximum=60.0,
        multiplier=2.0,
        deadline=300.0
    )
    def process_image(self, image_url, asset_id):
        self.set_asset_status(asset_id, 'processing')
        try:
            self.logger.info(f"Processing image: {image_url}")
            
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            # Download the image
            response = requests.get(image_url, timeout=30, headers=headers)
            if response.status_code != 200:
                self.logger.error(f"Failed to download image: {image_url} (Status: {response.status_code})")
                self.set_asset_status(asset_id, 'failed')
                return None

            # Create image object
            image = vision.Image(content=response.content)

            # Perform OCR with retry
            response = self.client.document_text_detection(image=image)
            document = response.full_text_annotation

            if response.error.message:
                raise Exception(f'Vision API error: {response.error.message}')

            # Save OCR result
            ocr_result = OCRResult(
                asset_id=asset_id,
                content=document.text,
                confidence=document.pages[0].confidence if document.pages else 0.0
            )
            db.session.add(ocr_result)
            self.set_asset_status(asset_id, 'processed')
            db.session.commit()

            self.logger.info(f"Successfully processed image: {image_url}")
            return ocr_result

        except Exception as e:
            self.logger.error(f"Error processing image {image_url}: {str(e)}")
            self.set_asset_status(asset_id, 'failed')
            db.session.rollback()
            return None

    @retry.Retry(
        predicate=retry.if_exception_type(GoogleAPIError),
        initial=1.0,
        maximum=60.0,
        multiplier=2.0,
        deadline=300.0
    )
    def process_pdf(self, pdf_url, asset_id):
        self.set_asset_status(asset_id, 'processing')
        try:
            self.logger.info(f"Processing PDF: {pdf_url}")
            
            # Create temporary directory for processing
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download the PDF
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                response = requests.get(pdf_url, timeout=30, headers=headers)
                if response.status_code != 200:
                    self.logger.error(f"Failed to download PDF: {pdf_url} (Status: {response.status_code})")
                    self.set_asset_status(asset_id, 'failed')
                    return None

                # Upload PDF to Google Cloud Storage
                bucket = self.storage_client.bucket(self.bucket_name)
                pdf_blob = bucket.blob(f"pdfs/{asset_id}.pdf")
                pdf_blob.upload_from_string(
                    response.content,
                    content_type='application/pdf'
                )

                # Configure PDF processing
                gcs_source = vision.GcsSource(uri=f"gs://{self.bucket_name}/pdfs/{asset_id}.pdf")
                input_config = vision.InputConfig(
                    gcs_source=gcs_source,
                    mime_type='application/pdf'
                )

                # Configure output
                gcs_destination = vision.GcsDestination(uri=f"gs://{self.bucket_name}/ocr_results/{asset_id}/")
                output_config = vision.OutputConfig(
                    gcs_destination=gcs_destination,
                    batch_size=100
                )

                # Perform OCR
                async_request = vision.AsyncAnnotateFileRequest(
                    input_config=input_config,
                    output_config=output_config,
                    features=[vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)]
                )

                operation = self.client.async_batch_annotate_files(requests=[async_request])
                operation.result(timeout=180)  # Wait for operation to complete

                # Read results
                results = []
                for output in bucket.list_blobs(prefix=f"ocr_results/{asset_id}/"):
                    content = output.download_as_string()
                    # Parse the JSON response and extract text
                    try:
                        response_data = json.loads(content.decode('utf-8'))
                        if 'responses' in response_data and response_data['responses']:
                            full_text = response_data['responses'][0].get('fullTextAnnotation', {}).get('text', '')
                            results.append(full_text)
                        else:
                            results.append(content.decode('utf-8'))
                    except json.JSONDecodeError:
                        results.append(content.decode('utf-8'))

                # Save OCR result
                ocr_result = OCRResult(
                    asset_id=asset_id,
                    content='\n'.join(results),
                    confidence=1.0  # PDF OCR confidence is not provided by the API
                )
                db.session.add(ocr_result)
                self.set_asset_status(asset_id, 'processed')
                db.session.commit()

                # Cleanup
                pdf_blob.delete()
                for output in bucket.list_blobs(prefix=f"ocr_results/{asset_id}/"):
                    output.delete()

                self.logger.info(f"Successfully processed PDF: {pdf_url}")
                return ocr_result

        except Exception as e:
            self.logger.error(f"Error processing PDF {pdf_url}: {str(e)}")
            self.set_asset_status(asset_id, 'failed')
            db.session.rollback()
            return None 