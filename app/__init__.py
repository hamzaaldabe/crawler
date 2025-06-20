from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from flask_restx import Api
from flask_jwt_extended import JWTManager
from app.config import Config
from flask_cors import CORS
from flask_migrate import Migrate

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
auth = HTTPBasicAuth()
jwt = JWTManager()
api = Api(
    title='Web Crawler API',
    version='1.0',
    description='A REST API for managing web crawling operations',
    doc='/api/swagger',
    prefix='/api'
)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Enable CORS for all origins and all methods
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
    
    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    api.init_app(app)

    # Register blueprints
    from app.routes.auth import auth_bp, auth_ns
    from app.routes.domains import domains_bp, domains_ns
    from app.routes.urls import urls_bp, urls_ns, domain_urls_ns
    from app.routes.crawler import crawler_bp, crawler_ns
    from app.routes.assets import assets_bp, assets_ns
    from app.routes.ocr import ocr_bp, ocr_ns

    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(domains_bp, url_prefix='/api')
    app.register_blueprint(urls_bp, url_prefix='/api')
    app.register_blueprint(crawler_bp, url_prefix='/api')
    app.register_blueprint(assets_bp, url_prefix='/api')
    app.register_blueprint(ocr_bp, url_prefix='/api')

    # Register namespaces
    api.add_namespace(auth_ns)
    api.add_namespace(domains_ns)
    api.add_namespace(urls_ns)
    api.add_namespace(domain_urls_ns)
    api.add_namespace(crawler_ns)
    api.add_namespace(assets_ns)
    api.add_namespace(ocr_ns)

    # Initialize scheduler
    from app.scheduler import init_scheduler
    init_scheduler(app)

    # Global error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not found'}, 404

    return app

__all__ = ['db', 'auth', 'create_app', 'api', 'jwt']
