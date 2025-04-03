from app import db
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
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
    url = db.Column(db.String(1024), nullable=False)
    status = db.Column(db.String(20), default='PENDING')
    domain_id = db.Column(db.Integer, db.ForeignKey('domain.id'), nullable=False)
    assets = db.relationship('Asset', backref='url', lazy=True)

class Asset(db.Model):
    __tablename__ = 'asset'
    id = db.Column(db.Integer, primary_key=True)
    asset_url = db.Column(db.String(1024), nullable=False)
    asset_type = db.Column(db.String(20))  # 'image' or 'pdf'
    status = db.Column(db.String(20), default='PENDING')
    url_id = db.Column(db.Integer, db.ForeignKey('url.id'), nullable=False)
