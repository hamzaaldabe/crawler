from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from app.config import Config

db = SQLAlchemy()
auth = HTTPBasicAuth()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)


    from app.routes.auth import auth_bp
    from app.routes.domains import domains_bp
    from app.routes.urls import urls_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(domains_bp)
    app.register_blueprint(urls_bp)

    from app.scheduler import init_scheduler
    init_scheduler(app)

    return app

__all__ = ['db', 'auth', 'create_app']
