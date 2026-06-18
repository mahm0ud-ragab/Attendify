import io
import csv
import random
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
from haversine import haversine, Unit

from flask import request, jsonify, Response, render_template, current_app, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import (
    User,
    Course,
    Session,
    Enrollment,
    Attendance,
    RoleEnum,
    CheckInEnum,
    ProjectorToken,
)

from app.attendance import attendance_bp


UNIVERSITY_UUID = "123e4567-e89b-12d3-a456-426614174000"
DEFAULT_MAJOR = 100


# ─────────────────────────────────────────────────────────────────────────────
# EXISTING ENDPOINTS  (unchanged – kept verbatim from original)
# ─────────────────────────────────────────────────────────────────────────────


@attendance_bp.route("/sessions/start", methods=["POST"])
@jwt_required()
def start_session():
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

    old_session = Session.query.filter_by(course_id=course_id, is_active=True).first()
    if old_session:
        old_session.is_active = False
        db.session.add(old_session)

    minor = _generate_unique_minor(DEFAULT_MAJOR)

    new_session = Session(
        course_id=course_id,
        lecturer_id=instructor.id,
        major=DEFAULT_MAJOR,
        minor=minor,
        is_active=True,
        qr_secret_key=pyotp.random_base32()
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

    timestamp_str = data.get("timestamp")
    if timestamp_str:
        try:
            scan_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except:
            return jsonify({"error": "Invalid timestamp format"}), 400
    else:
        scan_time = datetime.now(timezone.utc)

    enrollment = Enrollment.query.filter_by(
        student_id=student.id,
        course_id=selected_course_id
    ).first()

    if not enrollment:
        return jsonify({"error": "You are not enrolled in this course"}), 403

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

    existing = Attendance.query.filter_by(
        session_id=session.session_id,
        student_id=student.id
    ).first()

    if existing:
        return jsonify({
            "status": "already_marked",
            "message": "Attendance already recorded"
        }), 200

    new_log = Attendance(
        session_id=session.session_id,
        student_id=student.id,
        checkin_method=CheckInEnum.ble,
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
    Body:  { "session_id": 1 }
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

    session = db.session.get(Session, session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    if session.lecturer_id != instructor.id:
        return jsonify({"error": "You cannot end another lecturer's session"}), 403

    if not session.is_active:
        return jsonify({"error": "Session is already ended"}), 400

    session.is_active = False

    try:
        db.session.add(session)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Failed to end session", "details": str(exc)}), 500

    return jsonify({
        "status": "success",
        "message": "Session ended successfully",
        "session_id": session.session_id
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# NEW ── GET /api/attendance/stats/<course_id>
#
# Full statistical snapshot for every session in a course.
# Response shape:
# {
#   "course_id": int,
#   "course_title": str,
#   "total_enrolled": int,          ← how many students are enrolled RIGHT NOW
#   "total_sessions": int,
#   "overall_rate": float,          ← % across ALL sessions
#   "best_session": { … } | null,   ← session object with highest attended_count
#   "sessions": [                   ← newest first
#     {
#       "session_id": int,
#       "date": "YYYY-MM-DD HH:MM:SS",
#       "is_active": bool,
#       "attended_count": int,
#       "rate": float,              ← attended / enrolled × 100
#       "students": [
#         { "student_id", "name", "email", "scan_time" },
#         …
#       ]
#     },
#     …
#   ]
# }
# ─────────────────────────────────────────────────────────────────────────────
@attendance_bp.route("/attendance/stats/<int:course_id>", methods=["GET"])
@jwt_required()
def get_attendance_stats(course_id):
    current_user_id = int(get_jwt_identity())

    instructor = db.session.get(User, current_user_id)
    if not instructor:
        return jsonify({"error": "User not found"}), 404
    if instructor.role != RoleEnum.lecturer:
        return jsonify({"error": "Only lecturers can view attendance stats"}), 403

    course = db.session.get(Course, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404
    if course.lecturer_id != instructor.id:
        return jsonify({"error": "You are not the lecturer of this course"}), 403

    # ── enrolled count (current snapshot) ──
    total_enrolled = Enrollment.query.filter_by(course_id=course_id).count()

    # ── all sessions, newest first ──
    sessions = (
        Session.query
        .filter_by(course_id=course_id)
        .order_by(Session.created_at.desc())
        .all()
    )

    sessions_data   = []
    total_marks     = 0   # running sum for overall rate

    for sess in sessions:
        logs = (
            Attendance.query
            .filter_by(session_id=sess.session_id)
            .order_by(Attendance.scan_time.asc())
            .all()
        )

        attended = len(logs)
        total_marks += attended
        rate = round((attended / total_enrolled * 100), 1) if total_enrolled > 0 else 0.0

        students_list = []
        for log in logs:
            student = db.session.get(User, log.student_id)
            if student:
                students_list.append({
                    "student_id": student.id,
                    "name":       student.name,
                    "email":      student.email,
                    "scan_time":  log.scan_time.strftime("%Y-%m-%d %H:%M:%S") if log.scan_time else None,
                })

        sessions_data.append({
            "session_id":     sess.session_id,
            "date":           sess.created_at.strftime("%Y-%m-%d %H:%M:%S") if sess.created_at else None,
            "is_active":      sess.is_active,
            "attended_count": attended,
            "rate":           rate,
            "students":       students_list,
        })

    # ── overall rate ──
    total_possible = total_enrolled * len(sessions)
    overall_rate   = round((total_marks / total_possible * 100), 1) if total_possible > 0 else 0.0

    # ── best session ──
    best = max(sessions_data, key=lambda s: s["attended_count"]) if sessions_data else None

    return jsonify({
        "course_id":      course_id,
        "course_title":   course.title,
        "total_enrolled": total_enrolled,
        "total_sessions": len(sessions),
        "overall_rate":   overall_rate,
        "best_session":   best,
        "sessions":       sessions_data,
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# NEW ── GET /api/attendance/export/<course_id>/csv
#
# Query params (all optional – omit any to skip that filter):
#   session_id   – export only one specific session
#   start_date   – ISO date  YYYY-MM-DD  (inclusive)
#   end_date     – ISO date  YYYY-MM-DD  (inclusive, whole day)
#
# No filter at all → full course history.
#
# Response: application/csv attachment
# Columns:  Student Name | Student Email | Session ID | Session Date | Scan Time
# ─────────────────────────────────────────────────────────────────────────────
@attendance_bp.route("/attendance/export/<int:course_id>/csv", methods=["GET"])
@jwt_required()
def export_attendance_csv(course_id):
    current_user_id = int(get_jwt_identity())

    instructor = db.session.get(User, current_user_id)
    if not instructor:
        return jsonify({"error": "User not found"}), 404
    if instructor.role != RoleEnum.lecturer:
        return jsonify({"error": "Only lecturers can export attendance"}), 403

    course = db.session.get(Course, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404
    if course.lecturer_id != instructor.id:
        return jsonify({"error": "You are not the lecturer of this course"}), 403

    # ── optional query-string filters ──
    session_id_param = request.args.get("session_id")
    start_date_param = request.args.get("start_date")   # "YYYY-MM-DD"
    end_date_param   = request.args.get("end_date")     # "YYYY-MM-DD"

    # ── build session query ──
    session_query = Session.query.filter_by(course_id=course_id)

    if session_id_param:
        try:
            session_query = session_query.filter_by(session_id=int(session_id_param))
        except (ValueError, TypeError):
            return jsonify({"error": "session_id must be an integer"}), 400

    if start_date_param:
        try:
            start_dt = datetime.strptime(start_date_param, "%Y-%m-%d")
            session_query = session_query.filter(Session.created_at >= start_dt)
        except ValueError:
            return jsonify({"error": "start_date must be YYYY-MM-DD"}), 400

    if end_date_param:
        try:
            end_dt = datetime.strptime(end_date_param, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
            session_query = session_query.filter(Session.created_at <= end_dt)
        except ValueError:
            return jsonify({"error": "end_date must be YYYY-MM-DD"}), 400

    target_sessions = session_query.order_by(Session.created_at.asc()).all()

    # ── collect rows ──
    rows = []
    for sess in target_sessions:
        logs = (
            Attendance.query
            .filter_by(session_id=sess.session_id)
            .order_by(Attendance.scan_time.asc())
            .all()
        )
        for log in logs:
            student = db.session.get(User, log.student_id)
            if student:
                rows.append([
                    student.name,
                    student.email,
                    sess.session_id,
                    sess.created_at.strftime("%Y-%m-%d %H:%M:%S") if sess.created_at else "",
                    log.scan_time.strftime("%Y-%m-%d %H:%M:%S")   if log.scan_time  else "",
                ])

    # ── write CSV ──
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student Name", "Student Email", "Session ID", "Session Date", "Scan Time"])
    writer.writerows(rows)
    csv_body = output.getvalue()
    output.close()

    # ── safe filename ──
    safe = "".join(c if c.isalnum() or c in (" ", "-", "_") else "" for c in course.title)
    filename = f"Attendance_{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        csv_body,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@attendance_bp.route("/session/projector_token", methods=["POST"])
@jwt_required()
def generate_projector_token():
    """
    Generates a short-lived, single-use URL for the classroom projector.
    """
    current_user_id = int(get_jwt_identity())
    
    instructor = db.session.get(User, current_user_id)
    if not instructor or instructor.role != RoleEnum.lecturer:
        return jsonify({"error": "Only lecturers can generate projector tokens"}), 403
    
    data = request.get_json() or {}
    session_id = data.get("session_id")
    
    session = db.session.get(Session, session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if session.lecturer_id != instructor.id:
        return jsonify({"error": "You do not own this session"}), 403
    
    token_str = secrets.token_urlsafe(32)
    
    new_token = ProjectorToken(
        token = token_str,
        session_id = session.session_id,
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=60),
        is_used = False
    )
    
    try:
        db.session.add(new_token)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Failed to create projector token", "details": str(exc)}), 500
    
    projector_url = url_for(
        'attendance.projector_view', 
        token=token_str, 
        _external=True
    )
    
    return jsonify({
        "url": projector_url,
        "expires_in": 60
    }), 201


@attendance_bp.route("/projector/<token>", methods=["GET"])
def projector_view(token):
    """
    Serves the HTML page for the projector.
    Burns the token immediately upon access to prevent reuse.
    """
    
    token_entry = db.session.get(ProjectorToken, token)
    
    if not token_entry:
        return "Invalid Link", 404
    
    if token_entry.is_used:
        return "Link Already Used (Security Check Failed)", 403
    
    now = datetime.now(timezone.utc)
    expiration = token_entry.expires_at.replace(tzinfo=timezone.utc) if token_entry.expires_at.tzinfo is None else token_entry.expires_at
    
    if expiration < now:
        return "Link Expired", 403
    
    token_entry.is_used = True
    db.session.commit()
    
    session = db.session.get(Session, token_entry.session_id)
    course = session.course
    
    return render_template(
        "projector.html",
        qr_secret_key=session.qr_secret_key,
        course_name=course.title,
        session_id=session.session_id
    )


@attendance_bp.route("/verify_qr", methods=["POST"])
@jwt_required()
def verify_qr():
    """
    Validates Dynamic QR scan.
    Checks: TOTP validity -> Device Uniqueness -> GPS Geofence.
    """
    current_user_id = int(get_jwt_identity())
    student = db.session.get(User, current_user_id)
    
    if not student:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json() or {}
    
    token_from_qr = data.get('token')
    session_id    = data.get('session_id')
    device_id     = data.get('device_id')
    lat           = data.get('lat')
    lon           = data.get('long')
    
    if not all([token_from_qr, session_id, device_id]):
        return jsonify({"error": "Missing required fields (token, session_id, device_id)"}), 400
    
    session = db.session.get(Session, session_id)
    if not session or not session.is_active:
        return jsonify({"error": "Session is not active"}), 404
    
    # --- CHECK 1: DEVICE ID (Anti-Buddy Punching) ---
    existing_checkin = Attendance.query.filter_by(
        session_id = session_id,
        device_id = device_id
    ).first()
    
    if existing_checkin:
        if existing_checkin.student_id == student.id:
            return jsonify({"message": "Already checked in"}), 200
        else:
            return jsonify({"error": "This device has already been used for attendance!"}), 403
    
    # --- CHECK 2: GPS GEOFENCE (Anti-Remote) ---
    faculty = session.course.faculty
    if faculty and faculty.latitude and faculty.longitude:
        if lat is None or lon is None:
            return jsonify({"error": "Location data required for validation"}), 400
            
        student_loc = (float(lat), float(lon))
        campus_loc  = (faculty.latitude, faculty.longitude)
        
        distance = haversine(student_loc, campus_loc, unit=Unit.METERS)
        
        # Threshold: 500 Meters
        if distance > 500:
            return jsonify({
                "error": "Location check failed", 
                "details": f"You are {int(distance)}m away from campus (Max: 500m)"
            }), 403
    
    # --- CHECK 3: TOTP VALIDATION (Anti-Screenshot) ---
    if not session.qr_secret_key:
        return jsonify({"error": "QR verification not configured for this session"}), 500
    
    totp = pyotp.TOTP(session.qr_secret_key, interval=5)
    
    if not totp.verify(token_from_qr, valid_window=1):
        return jsonify({"error": "Invalid or Expired QR Code"}), 400
    
    existing_student_record = Attendance.query.filter_by(
        session_id=session_id,
        student_id=student.id
    ).first()
    
    if existing_student_record:
        return jsonify({"message": "Attendance updated"}), 200

    new_record = Attendance(
        session_id=session_id,
        student_id=student.id,
        device_id=device_id,
        checkin_method=CheckInEnum.qr,
        scan_time=datetime.now(timezone.utc)
    )
    
    db.session.add(new_record)
    db.session.commit()
    
    return jsonify({"message": "Check-in Successful!", "method": "QR"}), 201