import enum
import psycopg2
import datetime
from app import db
import sqlalchemy as sa
from sqlalchemy import Enum
from pydantic import EmailStr
from passlib.context import CryptContext
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import sessionmaker, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, UniqueConstraint, DateTime, Boolean


# engine = sa.create_engine("postgresql://neondb_owner:npg_O2hT0HyIbsUz@ep-autumn-thunder-admy76mb-pooler.c-2.us-east-1.aws.neon.tech/testDB?sslmode=require&channel_binding=require", echo=True)
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__truncate_error=False
)

class RoleEnum(enum.Enum):
    student = "student"
    lecturer = "lecturer"
    admin = "admin"

class CheckInEnum(enum.Enum):
    ble = "ble"
    qr = "qr"
    manual = "manual"

class User(db.Model):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), nullable=False)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculties.id"), nullable=True)
    
    courses_taught: Mapped[list["Course"]] = relationship("Course", back_populates="lecturer")
    enrollments: Mapped[list["Enrollment"]] = relationship("Enrollment", back_populates="student")
    attendance_history: Mapped[list["Attendance"]] = relationship("Attendance", back_populates="student", cascade="all, delete-orphan")
    faculty: Mapped["Faculties"] = relationship("Faculties", back_populates="users")
    
    enrolled_courses = association_proxy('enrollments', 'course', creator=lambda c: Enrollment(course=c))  
    attended_sessions = association_proxy('attendance_history', 'session')  
    
    def __repr__(self) -> str:
        return f"User(id={self.id}, name={self.name}, email={self.email}, role={self.role})"
    
    def set_password(self, raw_password: str):
        self.password = pwd_context.hash(raw_password)
        
    def verify_password(self, raw_password: str) -> bool:
        return pwd_context.verify(raw_password, self.password)


class Course(db.Model):
    __tablename__ = "courses"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(1024), nullable=True)
    lecturer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculties.id"), nullable=True)
    
    lecturer: Mapped["User"] = relationship("User", back_populates="courses_taught")
    enrollments: Mapped[list["Enrollment"]] = relationship("Enrollment", back_populates="course")
    attendance_history: Mapped[list["Attendance"]] = relationship("Attendance", back_populates="student", cascade="all, delete-orphan")
    faculty: Mapped["Faculties"] = relationship("Faculties", back_populates="courses")
    
    enrolled_students = association_proxy('enrollments', 'student', creator=lambda s: Enrollment(student=s))
    
    def __repr__(self) -> str:
        return f"Course(id={self.id}, title={self.title}, lecturer_id={self.lecturer_id})"


class Enrollment(db.Model):
    __tablename__ = "enrollments"
    
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    
    course: Mapped["Course"] = relationship("Course", back_populates="enrollments")
    student: Mapped["User"] = relationship("User", back_populates="enrollments")
    
    def __init__(self, course=None, student=None):
        self.course = course
        self.student = student

    def __repr__(self):
        return f"Enrollment(course_id={self.course_id}, student_id={self.student_id})"


class Session(db.Model):
    __tablename__ = "sessions"
    
    session_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    lecturer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime, server_default=sa.func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True, nullable=False)
    
    major: Mapped[int] = mapped_column(nullable=False)
    minor: Mapped[int] = mapped_column(nullable=False)
    
    qr_secret_key: Mapped[str] = mapped_column(String(64), nullable=True)
    
    course: Mapped["Course"] = relationship("Course")
    lecturer: Mapped["User"] = relationship("User")
    
    attendance_logs: Mapped[list["Attendance"]] = relationship("Attendance", back_populates="session", cascade="all, delete-orphan")
    
    attendees = association_proxy('attendance_logs', 'student')

    def __repr__(self) -> str:
        return f"Session(id={self.session_id}, major={self.major}, minor={self.minor})"


class Attendance(db.Model):
    __tablename__ = "attendance_logs"
    
    log_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.session_id"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    device_id: Mapped[str] = mapped_column(String(255), nullable=True) 
    checkin_method: Mapped[CheckInEnum] = mapped_column(Enum(CheckInEnum), nullable=False)
    
    scan_time: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=sa.func.now(), nullable=False)
    
    student: Mapped["User"] = relationship("User", back_populates="attendance_history")
    session: Mapped["Session"] = relationship("Session", back_populates="attendance_logs")
    
    __table_args__ = (
        UniqueConstraint('session_id', 'student_id', name='_unique_student_session'),
        UniqueConstraint('session_id', 'device_id', name='_unique_device_per_session'),
    )

    def __repr__(self) -> str:
        return f"Attendance(student={self.student_id}, session={self.session_id}, method={self.checkin_method})"


class Faculties(db.Model):
    __tablename__ = "faculties"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    
    longitude: Mapped[float] = mapped_column(nullable=True)
    latitude: Mapped[float] = mapped_column(nullable=True)
    
    
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="faculty")
    users: Mapped[list["User"]] = relationship("User", back_populates="faculty")
    
    def __repr__(self) -> str:
        return f"Faculties(id={self.id}, name={self.name})"


class ProjectorToken(db.Model):
    __tablename__ = "projector_tokens"
    
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.session_id"), nullable=False)
    
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=sa.func.now(), nullable=False)
    
    # Default expires in 60 seconds (Python-side logic is safer for migrations)
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=60), 
        nullable=False
    )
    
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"Token(session={self.session_id}, used={self.is_used})"
    