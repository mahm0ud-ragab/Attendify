import random
from datetime import datetime, timezone

from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import (
    User,
    Course,
    Session,
    Enrollment,
    Attendance,
    RoleEnum,
)

from app.attendance import attendance_bp


UNIVERSITY_UUID = "123e4567-e89b-12d3-a456-426614174000"
DEFAULT_MAJOR = 100


@attendance_bp.route("/sessions/start", methods=["POST"])
@jwt_required()
def start_session():
    # Identity is string → convert to int
    current_user_id = int(get_jwt_identity())

    instructor = db.session.get(User, current_user_id)
    if not instructor:
        return jsonify({"error": "User not found"}), 404

    if instructor.role != RoleEnum.lecturer:
        return jsonify({"error": "Only lecturers can start sessions"}), 403

    data = request.get_json() or {}
    course_id = data.get("course_id")

    try:
        course_id = int(course_id)
    except:
        return jsonify({"error": "course_id must be integer"}), 400

    course = db.session.get(Course, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    if course.lecturer_id != instructor.id:
        return jsonify({"error": "You are not the lecturer of this course"}), 403

    # Deactivate any previous active session for this course
    old_session = Session.query.filter_by(course_id=course_id, is_active=True).first()
    if old_session:
        old_session.is_active = False
        db.session.add(old_session)

    # Generate unique minor
    minor = _generate_unique_minor(DEFAULT_MAJOR)

    new_session = Session(
        course_id=course_id,
        lecturer_id=instructor.id,
        major=DEFAULT_MAJOR,
        minor=minor,
        is_active=True
    )

    try:
        db.session.add(new_session)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Failed to create session", "details": str(exc)}), 500

    return jsonify({
        "status": "success",
        "message": "Session started successfully",
        "session_id": new_session.session_id,
        "beacon_config": {
            "uuid": UNIVERSITY_UUID,
            "major": DEFAULT_MAJOR,
            "minor": minor
        }
    }), 201



def _generate_unique_minor(major):
    while True:
        candidate = random.randint(1, 65535)
        exists = Session.query.filter_by(
            major=major,
            minor=candidate,
            is_active=True
        ).first()
        if not exists:
            return candidate


@attendance_bp.route("/attendance/mark", methods=["POST"])
@jwt_required()
def mark_attendance():
    current_user_id = int(get_jwt_identity())

    student = db.session.get(User, current_user_id)
    if not student:
        return jsonify({"error": "User not found"}), 404

    if student.role != RoleEnum.student:
        return jsonify({"error": "Only students can mark attendance"}), 403

    data = request.get_json() or {}
    selected_course_id = data.get("selected_course_id")
    scanned = data.get("scanned_data") or {}

    major = scanned.get("major")
    minor = scanned.get("minor")

    try:
        selected_course_id = int(selected_course_id)
    except:
        return jsonify({"error": "selected_course_id must be integer"}), 400

    if major is None or minor is None:
        return jsonify({"error": "Beacon data missing"}), 400

    # Optional timestamp from client
    timestamp_str = data.get("timestamp")
    if timestamp_str:
        try:
            scan_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except:
            return jsonify({"error": "Invalid timestamp format"}), 400
    else:
        scan_time = datetime.now(timezone.utc)

    # Ensure student is enrolled
    enrollment = Enrollment.query.filter_by(
        student_id=student.id,
        course_id=selected_course_id
    ).first()

    if not enrollment:
        return jsonify({"error": "You are not enrolled in this course"}), 403

    # Find active session via beacon
    session = Session.query.filter_by(
        major=major,
        minor=minor,
        is_active=True
    ).first()

    if not session:
        return jsonify({"error": "No active session found for this beacon"}), 404

    if session.course_id != selected_course_id:
        return jsonify({
            "error": "Beacon does not match selected course",
            "session_course_id": session.course_id
        }), 400

    # Prevent duplicate attendance
    existing = Attendance.query.filter_by(
        session_id=session.session_id,
        student_id=student.id
    ).first()

    if existing:
        return jsonify({
            "status": "already_marked",
            "message": "Attendance already recorded"
        }), 200

    # Create attendance record
    new_log = Attendance(
        session_id=session.session_id,
        student_id=student.id,
        scan_time=scan_time
    )

    try:
        db.session.add(new_log)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Failed to record attendance", "details": str(exc)}), 500

    return jsonify({
        "status": "success",
        "message": "Attendance marked",
        "data": {
            "session_id": session.session_id,
            "course_id": selected_course_id,
            "student_id": student.id
        }
    }), 201


@attendance_bp.route("/sessions/end", methods=["POST"])
@jwt_required()
def end_session():
    """
    End an active session for the logged-in lecturer.
    Body:
    {
        "session_id": 1
    }
    """
    current_user_id = int(get_jwt_identity())

    instructor = db.session.get(User, current_user_id)
    if not instructor:
        return jsonify({"error": "User not found"}), 404

    if instructor.role != RoleEnum.lecturer:
        return jsonify({"error": "Only lecturers can end sessions"}), 403

    data = request.get_json() or {}
    session_id = data.get("session_id")

    try:
        session_id = int(session_id)
    except:
        return jsonify({"error": "session_id must be an integer"}), 400

    # ✨ Fetch session
    session = db.session.get(Session, session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    # ✨ Ensure session belongs to instructor
    if session.lecturer_id != instructor.id:
        return jsonify({"error": "You cannot end another lecturer's session"}), 403

    # ✨ Session must be active
    if not session.is_active:
        return jsonify({"error": "Session is already ended"}), 400

    # ✨ End session
    session.is_active = False

    try:
        db.session.add(session)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "error": "Failed to end session",
            "details": str(exc)
        }), 500

    return jsonify({
        "status": "success",
        "message": "Session ended successfully",
        "session_id": session.session_id
    }), 200