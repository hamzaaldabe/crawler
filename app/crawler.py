import re
import os
from urllib.parse import urljoin
from cloudscraper import create_scraper
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

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

    def is_image(self, url):
        return any(url.lower().endswith(ext) for ext in self.image_extensions)

    def is_pdf(self, url):
        return any(url.lower().endswith(ext) for ext in self.pdf_extensions)

    def save_asset(self, url, typ, url_entry):
        asset = Asset(url=url, asset_type=typ, url_id=url_entry.id)
        db.session.add(asset)
        db.session.commit()
        return asset

    def process_with_ocr(self, asset, is_pdf=False):
        if self.ocr_processor:
            if is_pdf:
                self.ocr_processor.process_pdf(asset.url, asset.id)
            else:
                self.ocr_processor.process_image(asset.url, asset.id)

    def fetch_dom(self, url):
        """
        Fetch DOM using Selenium with proper wait conditions.
        Returns final HTML string.
        """
        try:
            # Configure Chrome options
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument(f'user-agent={self.headers["User-Agent"]}')
            
            # Use Service object for driver initialization
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
            try:
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
                
                # Get the page source
                html = driver.page_source
                return html
                
            except Exception as e:
                print(f"Error during Selenium operations: {e}")
                return None
                
            finally:
                # Always quit the driver
                driver.quit()
                
        except Exception as e:
            print(f"Error initializing Selenium: {e}")
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

            for el in soup.find_all(style=True):
                style = el['style'] or ''
                if 'background-image' in style:
                    for match in re.findall(r'\((.*?)\)', style):
                        full = urljoin(base_url, match)
                        if self.is_image(full):
                            asset = self.save_asset(full, 'image', url_entry)
                            self.process_with_ocr(asset)

            for src in soup.find_all('source'):
                if src.get('srcset'):
                    full = urljoin(base_url, src['srcset'].split()[0])
                    if self.is_image(full):
                        asset = self.save_asset(full, 'image', url_entry)
                        self.process_with_ocr(asset)

            for a in soup.find_all('a', href=True):
                href = a['href']
                if self.is_pdf(href):
                    full = urljoin(base_url, href)
                    asset = self.save_asset(full, 'pdf', url_entry)
                    self.process_with_ocr(asset, is_pdf=True)

            url_entry.status = 'completed'
            db.session.commit()

        except Exception as e:
            print(f"Error crawling {url_entry.url}: {e}")
            url_entry.status = 'failed'
            db.session.commit()
