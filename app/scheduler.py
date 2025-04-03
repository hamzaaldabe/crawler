import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app
from app.models import URL
from app.crawler import crawl_url
from app import db

def process_pending_urls():
    current_app.logger.info("Processing pending URLs...")
    pending_urls = URL.query.filter_by(status='PENDING').all()
    for url_entry in pending_urls:
        crawl_url(url_entry)

def init_scheduler(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=process_pending_urls, trigger="interval", minutes=10)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
