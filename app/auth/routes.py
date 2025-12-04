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
from app.models import User, RoleEnum, Course, Enrollment
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

    # Return token immediately - FIXED: Convert ID to string
    access_token = create_access_token(
        identity=str(user.id),
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
        return jsonify({"message": "Invalid email or password."}), 401

    # FIXED: Convert ID to string
    access_token = create_access_token(
        identity=str(user.id),
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


# 🙋‍♂️ GET /auth/me (protected)
@auth_bp.get("/me")
@jwt_required()
def me():
    current_user_id = int(get_jwt_identity())
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


# 📚 GET /auth/courses/enrolled (for students)
@auth_bp.get("/courses/enrolled")
@jwt_required()
def get_enrolled_courses():
    """Get courses enrolled by the current student"""
    current_user_id = int(get_jwt_identity())
    user = db.session.get(User, current_user_id)
    
    if not user:
        return jsonify({"message": "User not found"}), 404
    
    if user.role.value != "student":
        return jsonify({"message": "Only students can access enrolled courses"}), 403
    
    enrollments = Enrollment.query.filter_by(student_id=current_user_id).all()
    
    courses = []
    for enrollment in enrollments:
        course = db.session.get(Course, enrollment.course_id)
        if course:
            lecturer = db.session.get(User, course.lecturer_id)
            courses.append({
                "id": course.id,
                "title": course.title,
                "description": course.description or "",
                "lecturer_name": lecturer.name if lecturer else "Unknown",
                "lecturer_id": course.lecturer_id
            })
    
    return jsonify({"courses": courses}), 200


# 👨‍🏫 GET /auth/courses/teaching (for lecturers)
@auth_bp.get("/courses/teaching")
@jwt_required()
def get_teaching_courses():
    """Get courses taught by the current lecturer"""
    current_user_id = int(get_jwt_identity())
    user = db.session.get(User, current_user_id)
    
    if not user:
        return jsonify({"message": "User not found"}), 404
    
    if user.role.value != "lecturer":
        return jsonify({"message": "Only lecturers can access teaching courses"}), 403
    
    courses = Course.query.filter_by(lecturer_id=current_user_id).all()
    
    courses_data = []
    for course in courses:
        enrolled_count = Enrollment.query.filter_by(course_id=course.id).count()
        
        courses_data.append({
            "id": course.id,
            "title": course.title,
            "description": course.description or "",
            "enrolled_count": enrolled_count
        })
    
    return jsonify({"courses": courses_data}), 200


# 📖 GET /auth/courses/<id> (course details)
@auth_bp.get("/courses/<int:course_id>")
@jwt_required()
def get_course_details(course_id):
    """Get detailed information about a specific course"""
    current_user_id = int(get_jwt_identity())
    user = db.session.get(User, current_user_id)
    
    if not user:
        return jsonify({"message": "User not found"}), 404
    
    course = db.session.get(Course, course_id)
    if not course:
        return jsonify({"message": "Course not found"}), 404
    
    if user.role.value == "student":
        enrollment = Enrollment.query.filter_by(
            student_id=current_user_id,
            course_id=course_id
        ).first()
        if not enrollment:
            return jsonify({"message": "You are not enrolled in this course"}), 403
    elif user.role.value == "lecturer":
        if course.lecturer_id != current_user_id:
            return jsonify({"message": "You are not the lecturer of this course"}), 403
    
    lecturer = db.session.get(User, course.lecturer_id)
    
    enrollments = Enrollment.query.filter_by(course_id=course_id).all()
    enrolled_students = []
    for enrollment in enrollments:
        student = db.session.get(User, enrollment.student_id)
        if student:
            enrolled_students.append({
                "id": student.id,
                "name": student.name,
                "email": student.email
            })
    
    return jsonify({
        "id": course.id,
        "title": course.title,
        "description": course.description or "",
        "lecturer": {
            "id": lecturer.id,
            "name": lecturer.name,
            "email": lecturer.email
        } if lecturer else None,
        "enrolled_students": enrolled_students,
        "enrolled_count": len(enrolled_students)
    }), 200