import enum
import psycopg2
from app import db
import sqlalchemy as sa
from sqlalchemy import Enum
from pydantic import EmailStr
from sqlalchemy import String, ForeignKey
from passlib.context import CryptContext
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import sessionmaker, Mapped, mapped_column, relationship
from typing import Optional


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

class User(db.Model):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), nullable=False)
    
    courses_taught: Mapped[list["Course"]] = relationship("Course", back_populates="lecturer")
    enrollments: Mapped[list["Enrollment"]] = relationship("Enrollment", back_populates="student")
    
    enrolled_courses = association_proxy('enrollments', 'course', creator=lambda c: Enrollment(course=c))    
    
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
    
    lecturer: Mapped["User"] = relationship("User", back_populates="courses_taught")
    enrollments: Mapped[list["Enrollment"]] = relationship("Enrollment", back_populates="course")
    
    enrolled_students = association_proxy('enrollments', 'student', creator=lambda s: Enrollment(student=s))
    
    def __repr__(self) -> str:
        return f"Course(id={self.id}, title={self.title}, lecturer_id={self.lecturer_id})"


class Enrollment(db.Model):
    __tablename__ = "enrollments"
    
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    
    course: Mapped["Course"] = relationship("Course", back_populates="enrollments")
    student: Mapped["User"] = relationship("User", back_populates="enrollments")

    def _init_(self, course=None, student=None):
        self.course = course
        self.student = student

    def __repr__(self):
        return f"Enrollment(course_id={self.course_id}, student_id={self.student_id})"



# Base.metadata.create_all(engine)
# SessionLocal = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)

# def get_db_session():
#     session = SessionLocal()
#     try:
#         yield session
#     finally:
#         session.close()
        
# if __name__ == "__main__":
#     # Example usage
#     with SessionLocal() as session:
        # new_user_1 = User(name="mido absalam", email="mido@gmail.com", role=RoleEnum.admin)
        # new_user_2 = User(name="ahmed ragab", email="aragab@gmail.com", role=RoleEnum.student)
        # new_user_3 = User(name="mahmoud ragab", email="mragab@gmail.com", role=RoleEnum.admin)
        # new_user_4 = User(name="ahmed badawy", email="badawy@gmail.com", role=RoleEnum.lecturer)
        # fake_user = User(name="John Doe", email="mido@gmail.com", role=RoleEnum.admin)
        # fake_user.set_password("securepassword123")
        
        # new_user_1.set_password("securepassword123")
        # new_user_2.set_password("mypassword456")
        # new_user_3.set_password("adminpassword789")
        # new_user_4.set_password("lecturerpassword012")
        
        # session.add(new_user_1)
        # session.add(new_user_2)
        # session.add(new_user_3)
        # session.add(new_user_4)
        # session.add(fake_user)
        
        # session.commit()
        
        # print("\n\n")
        # print(f"Created users: {new_user_1}, {new_user_2}, {new_user_3}, {new_user_4}")
        # print("\n\n")
        
        # fetched_user = session.query(User).filter_by(id=4).first()
        # print(f"\n\nFetched user: {fetched_user}\n\n")
        
        # print(f"\n\navailable courses for {fetched_user.name}: {fetched_user.courses}\n\n")
        
        # print(fetched_user.verify_password("securepassword123"))  # Should return True
        # print(new_user_2.verify_password("wrongpassword"))  # Should return False
        
        # new_course = Course(title="Database Systems", description="An introduction to database systems.", lecturer_id=4)
        # session.add(new_course)
        # session.commit()
        
        # fetched_course = session.query(Course).first()
        # print(f"fetched course: {fetched_course}")
        # print(f"Lecturer of the course: {fetched_course.lecturer}")

    
        