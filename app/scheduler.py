import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.crawler import Crawler
from app.models import URL
from app import db
from flask import current_app

def init_scheduler(app):
    scheduler = BackgroundScheduler()
    
    def crawl_pending_urls():
        with app.app_context():
            try:
                # Get all pending URLs
                pending_urls = URL.query.filter_by(status='pending').all()
                
                if not pending_urls:
                    current_app.logger.info("No pending URLs to process")
                    return
                
                current_app.logger.info(f"Processing {len(pending_urls)} pending URLs")
                
                # Initialize crawler
                crawler = Crawler(app)
                
                # Process each URL
                for url in pending_urls:
                    try:
                        current_app.logger.info(f"Processing URL: {url.url}")
                        crawler.crawl_url(url)
                    except Exception as e:
                        current_app.logger.error(f"Error processing URL {url.url}: {str(e)}")
                        url.status = 'failed'
                        db.session.commit()
                
            except Exception as e:
                current_app.logger.error(f"Error in crawl_pending_urls job: {str(e)}")
    
    # Add the job to run every hour
    scheduler.add_job(
        func=crawl_pending_urls,
        trigger=IntervalTrigger(hours=1),
        id='crawl_pending_urls',
        name='Crawl pending URLs',
        replace_existing=True
    )
    
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    return scheduler
