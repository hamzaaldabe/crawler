import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app
from app.models import URL
from app.crawler import Crawler
from app import db

def init_scheduler(app):
    scheduler = BackgroundScheduler()
    crawler = Crawler()

    def crawl_pending_urls():
        with app.app_context():
            pending_urls = URL.query.filter_by(status='pending').all()
            for url in pending_urls:
                crawler.crawl_url(url)

    scheduler.add_job(func=crawl_pending_urls, trigger="interval", seconds=60)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
