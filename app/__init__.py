# app/__init__.py

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from app.config import Config

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()


def create_app(config_class=Config):
    """
    App Factory function to create and configure the Flask application.
    """
    app = Flask(__name__)

    app.config.from_object(config_class)
    
    # Enable CORS for all routes
    CORS(app, resources={r"/*": {"origins": "*"}})

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # Import models so that SQLAlchemy knows about them
    from app import models  # noqa: F401

    # JWT error handlers
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        print("JWT: Token expired")
        return jsonify({"message": "Token has expired"}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        print(f"JWT: Invalid token error: {error}")
        return jsonify({"message": f"Invalid token: {str(error)}"}), 422

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        print(f"JWT: Missing token error: {error}")
        return jsonify({"message": "Missing authorization token"}), 401
    
    @jwt.token_verification_failed_loader
    def token_verification_failed_callback(jwt_header, jwt_payload):
        print(f"JWT: Token verification failed - Header: {jwt_header}, Payload: {jwt_payload}")
        return jsonify({"message": "Token verification failed"}), 422

    # Register blueprints
    from app.auth import auth_bp
    app.register_blueprint(auth_bp)

    # Register attendance routes
    from app.attendance import attendance_bp
    app.register_blueprint(attendance_bp)

    return app