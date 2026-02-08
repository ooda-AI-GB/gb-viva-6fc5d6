from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
import datetime
import enum

DATABASE_URL = "sqlite:///./data/feedback.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    SUPPORT = "support"
    ADMIN = "admin"

class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class Status(str, enum.Enum):
    NEW = "new"
    IN_REVIEW = "in-review"
    RESOLVED = "resolved"
    CLOSED = "closed"

class Category(str, enum.Enum):
    BUG = "bug"
    FEATURE = "feature"
    COMPLAINT = "complaint"
    PRAISE = "praise"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String)  # stored as string for simplicity

    feedbacks = relationship("Feedback", back_populates="user")
    responses = relationship("Response", back_populates="user")

class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    category = Column(String)
    priority = Column(String)
    status = Column(String, default=Status.NEW)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    user = relationship("User", back_populates="feedbacks")
    responses = relationship("Response", back_populates="feedback", cascade="all, delete-orphan")

class Response(Base):
    __tablename__ = "responses"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    feedback_id = Column(Integer, ForeignKey("feedbacks.id"))
    user_id = Column(Integer, ForeignKey("users.id"))

    feedback = relationship("Feedback", back_populates="responses")
    user = relationship("User", back_populates="responses")

def init_db():
    Base.metadata.create_all(bind=engine)
