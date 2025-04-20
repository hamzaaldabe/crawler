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
from app.models import OCRResult
from flask import current_app
import tempfile

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

    @retry.Retry(
        predicate=retry.if_exception_type(GoogleAPIError),
        initial=1.0,
        maximum=60.0,
        multiplier=2.0,
        deadline=300.0
    )
    def process_image(self, image_url, asset_id):
        try:
            self.logger.info(f"Processing image: {image_url}")
            
            # Download the image
            response = requests.get(image_url, timeout=30)
            if response.status_code != 200:
                self.logger.error(f"Failed to download image: {image_url}")
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
                confidence=response.text_annotations[0].confidence if response.text_annotations else 0.0
            )
            db.session.add(ocr_result)
            db.session.commit()

            self.logger.info(f"Successfully processed image: {image_url}")
            return ocr_result

        except Exception as e:
            self.logger.error(f"Error processing image {image_url}: {str(e)}")
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
        try:
            self.logger.info(f"Processing PDF: {pdf_url}")
            
            # Create temporary directory for processing
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download the PDF
                response = requests.get(pdf_url, timeout=30)
                if response.status_code != 200:
                    self.logger.error(f"Failed to download PDF: {pdf_url}")
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
                    results.append(content.decode('utf-8'))

                # Save OCR result
                ocr_result = OCRResult(
                    asset_id=asset_id,
                    content='\n'.join(results),
                    confidence=1.0  # PDF OCR confidence is not provided by the API
                )
                db.session.add(ocr_result)
                db.session.commit()

                # Cleanup
                pdf_blob.delete()
                for output in bucket.list_blobs(prefix=f"ocr_results/{asset_id}/"):
                    output.delete()

                self.logger.info(f"Successfully processed PDF: {pdf_url}")
                return ocr_result

        except Exception as e:
            self.logger.error(f"Error processing PDF {pdf_url}: {str(e)}")
            db.session.rollback()
            return None 