import requests
from bs4 import BeautifulSoup
from validators import url as validate_url
from flask import current_app
from app import db
from app.models import URL, Asset

def crawl_url(url_entry):
    try:
        response = requests.get(url_entry.url, timeout=10)
        if response.status_code != 200:
            return
        soup = BeautifulSoup(response.text, 'html.parser')
        img_tags = soup.find_all('img')
        for img in img_tags:
            img_src = img.get('src')
            if img_src and validate_url(img_src):
                asset = Asset(asset_url=img_src, asset_type='image', url=url_entry)
                db.session.add(asset)
        a_tags = soup.find_all('a', href=True)
        for a in a_tags:
            href = a['href']
            if href.lower().endswith('.pdf') and validate_url(href):
                asset = Asset(asset_url=href, asset_type='pdf', url=url_entry)
                db.session.add(asset)
        url_entry.status = 'CRAWLED'
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Error crawling URL {url_entry.url}: {str(e)}")
