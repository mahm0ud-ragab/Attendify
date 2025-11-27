# app/__init__.py

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
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

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # Import models so that SQLAlchemy knows about them
    from app import models  # noqa: F401

    # Register blueprints
    from app.auth import auth_bp
    app.register_blueprint(auth_bp)

    return app
