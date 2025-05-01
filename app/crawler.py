import re
import os
import time
from urllib.parse import urljoin
from cloudscraper import create_scraper
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from flask import current_app

from app import db
from app.models import URL, Asset
from app.ocr import OCRProcessor

class Crawler:
    def __init__(self, app=None):
        self.app = app
        if app:
            with app.app_context():
                self.ocr_processor = OCRProcessor()
        else:
            self.ocr_processor = None

        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg'}
        self.pdf_extensions   = {'.pdf'}
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/114.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
        }
        self.page_load_timeout = 30  # seconds
        self.script_timeout = 30     # seconds
        self.max_retries = 3         # number of retries for failed requests

    def is_image(self, url):
        return any(url.lower().endswith(ext) for ext in self.image_extensions)

    def is_pdf(self, url):
        return any(url.lower().endswith(ext) for ext in self.pdf_extensions)

    def save_asset(self, url, typ, url_entry):
        try:
            asset = Asset(url=url, asset_type=typ, url_id=url_entry.id)
            db.session.add(asset)
            db.session.commit()
            return asset
        except Exception as e:
            current_app.logger.error(f"Error saving asset {url}: {str(e)}")
            db.session.rollback()
            return None

    def process_with_ocr(self, asset, is_pdf=False):
        if self.ocr_processor and asset:
            try:
                if is_pdf:
                    self.ocr_processor.process_pdf(asset.url, asset.id)
                else:
                    self.ocr_processor.process_image(asset.url, asset.id)
            except Exception as e:
                current_app.logger.error(f"Error processing OCR for asset {asset.url}: {str(e)}")

    def fetch_dom(self, url):
        """
        Fetch DOM using Selenium with proper wait conditions and retries.
        Returns final HTML string.
        """
        driver = None
        for attempt in range(self.max_retries):
            try:
                # Configure Chrome options
                options = Options()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                options.add_argument('--window-size=1920,1080')
                options.add_argument(f'user-agent={self.headers["User-Agent"]}')
                
                # Use Service object for driver initialization
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
                
                # Set timeouts
                driver.set_page_load_timeout(self.page_load_timeout)
                driver.set_script_timeout(self.script_timeout)
                
                # Navigate to the URL
                driver.get(url)
                
                # Wait for the page to load
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, 'body'))
                )
                
                # Wait for images to load
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                
                # Additional wait for dynamic content
                time.sleep(2)
                
                # Get the page source
                html = driver.page_source
                return html
                
            except TimeoutException as e:
                current_app.logger.warning(f"Timeout on attempt {attempt + 1} for {url}: {str(e)}")
                if attempt == self.max_retries - 1:
                    current_app.logger.error(f"All attempts timed out for {url}")
                    return None
                time.sleep(2 ** attempt)  # Exponential backoff
                
            except WebDriverException as e:
                current_app.logger.error(f"WebDriver error on attempt {attempt + 1} for {url}: {str(e)}")
                if attempt == self.max_retries - 1:
                    return None
                time.sleep(2 ** attempt)
                
            except Exception as e:
                current_app.logger.error(f"Unexpected error on attempt {attempt + 1} for {url}: {str(e)}")
                if attempt == self.max_retries - 1:
                    return None
                time.sleep(2 ** attempt)
                
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception as e:
                        current_app.logger.error(f"Error quitting driver: {str(e)}")
        
        return None

    def crawl_url(self, url_entry: URL):
        try:
            html = self.fetch_dom(url_entry.url)
            if not html:
                url_entry.status = 'failed'
                db.session.commit()
                return

            soup = BeautifulSoup(html, 'html.parser')
            base_url = url_entry.url

            # Process images
            for img in soup.find_all('img'):
                for attr in ('src', 'data-src'):
                    src = img.get(attr)
                    if src:
                        full = urljoin(base_url, src)
                        if self.is_image(full):
                            asset = self.save_asset(full, 'image', url_entry)
                            self.process_with_ocr(asset)

                if img.get('srcset'):
                    for candidate in img['srcset'].split(','):
                        full = urljoin(base_url, candidate.strip().split()[0])
                        if self.is_image(full):
                            asset = self.save_asset(full, 'image', url_entry)
                            self.process_with_ocr(asset)

            # Process background images
            for el in soup.find_all(style=True):
                style = el['style'] or ''
                if 'background-image' in style:
                    for match in re.findall(r'\((.*?)\)', style):
                        full = urljoin(base_url, match)
                        if self.is_image(full):
                            asset = self.save_asset(full, 'image', url_entry)
                            self.process_with_ocr(asset)

            # Process source elements
            for src in soup.find_all('source'):
                if src.get('srcset'):
                    full = urljoin(base_url, src['srcset'].split()[0])
                    if self.is_image(full):
                        asset = self.save_asset(full, 'image', url_entry)
                        self.process_with_ocr(asset)

            # Process PDFs
            for a in soup.find_all('a', href=True):
                href = a['href']
                if self.is_pdf(href):
                    full = urljoin(base_url, href)
                    asset = self.save_asset(full, 'pdf', url_entry)
                    self.process_with_ocr(asset, is_pdf=True)

            url_entry.status = 'completed'
            db.session.commit()

        except Exception as e:
            current_app.logger.error(f"Error crawling {url_entry.url}: {str(e)}")
            url_entry.status = 'failed'
            db.session.commit()
