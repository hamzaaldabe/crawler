from flask import Blueprint, request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app import db, auth, api, jwt
from app.models import User
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)
auth_ns = Namespace('auth', description='Authentication operations', path='/')

# Swagger models
user_model = api.model('User', {
    'username': fields.String(required=True, description='Username'),
    'password': fields.String(required=True, description='Password')
})

user_response = api.model('UserResponse', {
    'id': fields.Integer(description='User ID'),
    'username': fields.String(description='Username')
})

login_response = api.model('LoginResponse', {
    'access_token': fields.String(description='JWT Access Token'),
    'user': fields.Nested(user_response, description='User information')
})

@auth_ns.route('/signup')
class Signup(Resource):
    @auth_ns.expect(user_model)
    @auth_ns.response(201, 'User created successfully')
    @auth_ns.response(400, 'Invalid input')
    def post(self):
        """Create a new user"""
        data = request.get_json() or {}
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return {'error': 'Missing username or password'}, 400
        if User.query.filter_by(username=username).first():
            return {'error': 'User already exists'}, 400
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return {
            'message': 'User created successfully',
            'user': {
                'id': user.id,
                'username': user.username
            }
        }, 201

@auth_ns.route('/login')
class Login(Resource):
    @auth_ns.expect(user_model)
    @auth_ns.response(200, 'Login successful', login_response)
    @auth_ns.response(401, 'Invalid credentials')
    def post(self):
        """Login user and get JWT token"""
        data = request.get_json() or {}
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return {'error': 'Invalid username or password'}, 401
            
        access_token = create_access_token(identity=user)
        return {
            'access_token': access_token,
            'user': {
                'id': user.id,
                'username': user.username
            }
        }, 200

@jwt.user_identity_loader
def user_identity_lookup(user):
    if isinstance(user, User):
        return str(user.id)
    return str(user)

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    return User.query.filter_by(id=int(identity)).first()
