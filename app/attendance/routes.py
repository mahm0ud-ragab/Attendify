import random
from flask import request, jsonify
from app import app, db
from models import Session, Course, User

UNIVERSITY_UUID = "123e4567-e89b-12d3-a456-426614174000"

@app.route('api/sessions/start', methods=['POST'])
def start_session():
    data = request.get_json()
    course_id = data.get('course_id')
    instructor_id = data.get('user_id')
    major_id = 123  # Example major ID SHOULD BE REPLACED WITH ACTUAL LOGIC TO GET MAJOR ID
    
    if not course_id or not instructor_id:
        return jsonify({"error": "course_id and user_id are required"}), 400
    
    course = db.session.get(Course, course_id)
    
    if not course:
        return jsonify({"error": "Course not found"}), 404
    
    if instructor_id != course.lecturer_id:
        return jsonify({"error": "User is not the instructor for this course"}), 403
    
    existing_session = db.session.query(Session).filter_by(
        course_id=course_id,
        is_active=True
    ).first()
    
    if existing_session:
        existing_session.is_active = False
        db.session.commit()
    
    while True:
        random_minor = random.randint(1, 65535)
        
        collision = db.session.query(Session).filter_by(
            major_id=major_id,
            minor_id=random_minor,
            is_active=True
        ).first()
        
        if not collision:
            break
    
    new_session = Session(
        course_id=course_id,
        lecturer_id=instructor_id,
        major=major_id,
        minor=random_minor,
        is_active=True
    )
    
    try:
        db.session.add(new_session)
        db.session.commit()
        
        return jsonify({
            "message": "Session started successfully",
            "session_id": new_session.session_id,
            "beacon_data": {
                "uuid": UNIVERSITY_UUID,
                "major": major_id,
                "minor": random_minor
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to start session", "details": str(e)}), 500