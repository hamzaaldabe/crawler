from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.Text)
    domains = db.relationship('Domain', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Domain(db.Model):
    __tablename__ = 'domain'
    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    urls = db.relationship('URL', backref='domain', lazy=True)

class URL(db.Model):
    __tablename__ = 'url'
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(2048), nullable=False)
    domain_id = db.Column(db.Integer, db.ForeignKey('domain.id'), nullable=False)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    assets = db.relationship('Asset', backref='parent_url', lazy=True)

    @classmethod
    def get_assets_by_url_id(cls, url_id):
        """
        Get all assets associated with a specific URL ID.
        
        Args:
            url_id (int): The ID of the URL to get assets for
            
        Returns:
            list: A list of Asset objects associated with the URL
            None: If the URL ID doesn't exist
            
        Example:
            >>> assets = URL.get_assets_by_url_id(1)
            >>> for asset in assets:
            ...     print(asset.url)
        """
        url = cls.query.get(url_id)
        if url:
            return url.assets
        return None

class Asset(db.Model):
    __tablename__ = 'asset'
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(2048), nullable=False)
    asset_type = db.Column(db.String(20))  # 'image' or 'pdf'
    status = db.Column(db.String(20), default='pending')
    url_id = db.Column(db.Integer, db.ForeignKey('url.id'), nullable=False)
    ocr_results = db.relationship('OCRResult', backref='asset', lazy=True)

    @classmethod
    def get_ocr_results_by_asset_id(cls, asset_id):
        """
        Get all OCR results for a specific asset.
        
        Args:
            asset_id (int): The ID of the asset to get OCR results for
            
        Returns:
            list: A list of OCRResult objects for the asset
            None: If the asset ID doesn't exist
            
        Example:
            >>> results = Asset.get_ocr_results_by_asset_id(1)
            >>> for result in results:
            ...     print(result.content)
        """
        asset = cls.query.get(asset_id)
        if asset:
            return asset.ocr_results
        return None

class OCRResult(db.Model):
    __tablename__ = 'ocr_result'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    content = db.Column(db.Text)
    confidence = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
