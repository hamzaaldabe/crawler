import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from flask import current_app
from app.models import URL
from app.crawler import Crawler
from app import db

def init_scheduler(app):
    # Configure the scheduler
    jobstores = {
        'default': MemoryJobStore()
    }
    executors = {
        'default': ThreadPoolExecutor(20)  # Allow up to 20 concurrent jobs
    }
    job_defaults = {
        'coalesce': True,  # Combine multiple waiting jobs into one
        'max_instances': 1,  # Only one instance of each job can run at a time
        'misfire_grace_time': 60  # Jobs can be 60 seconds late before being considered misfired
    }

    scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults
    )
    
    crawler = Crawler(app)

    def crawl_pending_urls():
        with app.app_context():
            try:
                pending_urls = URL.query.filter_by(status='pending').all()
                for url in pending_urls:
                    try:
                        crawler.crawl_url(url)
                    except Exception as e:
                        current_app.logger.error(f"Error crawling URL {url.url}: {str(e)}")
                        # Update URL status to failed
                        url.status = 'failed'
                        db.session.commit()
            except Exception as e:
                current_app.logger.error(f"Error in crawl_pending_urls job: {str(e)}")

    # Add the job with a unique ID
    scheduler.add_job(
        func=crawl_pending_urls,
        trigger="interval",
        hours=1,  # Run every hour instead of every minute
        id='crawl_pending_urls',
        replace_existing=True  # Replace the job if it already exists
    )
    
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
