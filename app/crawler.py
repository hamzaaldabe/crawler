import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from app import db
from app.models import URL, Asset
from app.ocr import OCRProcessor
import os

class Crawler:
    def __init__(self):
        self.ocr_processor = OCRProcessor()
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
        self.pdf_extensions = {'.pdf'}

    def is_image(self, url):
        return any(url.lower().endswith(ext) for ext in self.image_extensions)

    def is_pdf(self, url):
        return any(url.lower().endswith(ext) for ext in self.pdf_extensions)

    def crawl_url(self, url_entry):
        try:
            response = requests.get(url_entry.url)
            if response.status_code != 200:
                url_entry.status = 'failed'
                db.session.commit()
                return

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Process images
            for img in soup.find_all('img'):
                img_url = urljoin(url_entry.url, img.get('src', ''))
                if self.is_image(img_url):
                    asset = Asset(url=img_url, asset_type='image', url_id=url_entry.id)
                    db.session.add(asset)
                    db.session.commit()  # Commit to get asset.id
                    # Process with OCR
                    self.ocr_processor.process_image(img_url, asset.id)

            # Process PDFs
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if self.is_pdf(href):
                    pdf_url = urljoin(url_entry.url, href)
                    asset = Asset(url=pdf_url, asset_type='pdf', url_id=url_entry.id)
                    db.session.add(asset)
                    db.session.commit()  # Commit to get asset.id
                    # Process with OCR
                    self.ocr_processor.process_pdf(pdf_url, asset.id)

            url_entry.status = 'completed'
            db.session.commit()

        except Exception as e:
            print(f"Error crawling {url_entry.url}: {str(e)}")
            url_entry.status = 'failed'
            db.session.commit()
