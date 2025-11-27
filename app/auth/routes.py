# app/auth/routes.py

from flask import request, jsonify
from pydantic import ValidationError
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
)
from datetime import timedelta

from app import db
from app.models import User, RoleEnum
from app.auth import auth_bp
from app.auth.schemas import RegisterSchema, LoginSchema


# 👤 POST /auth/register
@auth_bp.post("/register")
def register():
    data = request.get_json() or {}

    try:
        body = RegisterSchema(**data)
    except ValidationError as e:
        return jsonify({"errors": e.errors()}), 400

    # ❌ Admins are created manually, not via public endpoint
    if body.role == "admin":
        return (
            jsonify(
                {
                    "message": "You cannot register as admin via this endpoint. "
                    "Ask an existing admin to create your account."
                }
            ),
            403,
        )

    # Check if email already exists
    existing = User.query.filter_by(email=body.email).first()
    if existing:
        return jsonify({"message": "Email is already registered."}), 409

    # Create user
    user = User(
        name=body.name,
        email=body.email,
        role=RoleEnum(body.role),
    )
    user.set_password(body.password)

    db.session.add(user)
    db.session.commit()

    # Optionally return a token immediately
    access_token = create_access_token(
        identity=user.id,
        additional_claims={"role": user.role.value, "name": user.name},
        expires_delta=timedelta(hours=1),
    )

    return (
        jsonify(
            {
                "message": "User registered successfully.",
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role": user.role.value,
                },
                "access_token": access_token,
            }
        ),
        201,
    )


# 🔑 POST /auth/login
@auth_bp.post("/login")
def login():
    data = request.get_json() or {}

    try:
        body = LoginSchema(**data)
    except ValidationError as e:
        return jsonify({"errors": e.errors()}), 400

    user = User.query.filter_by(email=body.email).first()
    if not user or not user.verify_password(body.password):
        # Don't reveal which one is wrong
        return jsonify({"message": "Invalid email or password."}), 401

    access_token = create_access_token(
        identity=user.id,
        additional_claims={"role": user.role.value, "name": user.name},
        expires_delta=timedelta(hours=1),
    )

    return jsonify(
        {
            "message": "Login successful.",
            "access_token": access_token,
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": user.role.value,
            },
        }
    )


# 🙋‍♂️ GET /auth/me  (protected)
@auth_bp.get("/me")
@jwt_required()
def me():
    current_user_id = get_jwt_identity()
    user = db.session.get(User, current_user_id)

    if not user:
        return jsonify({"message": "User not found."}), 404

    return jsonify(
        {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role.value,
        }
    )
