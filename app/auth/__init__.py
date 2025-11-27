# app/auth/__init__.py

from flask import Blueprint

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# Import routes so they get registered on the blueprint
from app.auth import routes  # noqa: E402,F401
