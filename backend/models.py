from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)

    chat_threads = relationship("ChatThread", back_populates="user", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="user", cascade="all, delete-orphan")
    passports = relationship("Passport", back_populates="user", cascade="all, delete-orphan")
    visas = relationship("Visa", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_users_email', 'email', unique=True),
    )

class EmailOTP(Base):
    __tablename__ = "email_otps"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String, nullable=False, index=True)
    otp_code = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_email_otps_email', 'email'),
    )

class ChatThread(Base):
    __tablename__ = "chat_threads"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    thread_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    state = Column(JSONB, nullable=True, default={})
    user = relationship("User", back_populates="chat_threads")
    messages = relationship("ChatMessage", back_populates="thread", cascade="all, delete-orphan", order_by="ChatMessage.message_order")
    invoices = relationship("Invoice", back_populates="thread", cascade="all, delete-orphan")
    passports = relationship("Passport", back_populates="thread", cascade="all, delete-orphan")
    visas = relationship("Visa", back_populates="thread", cascade="all, delete-orphan")
    

    __table_args__ = (
        Index('ix_chat_threads_thread_id', 'thread_id', unique=True),
        Index('ix_chat_threads_user_id', 'user_id'),
    )

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    thread_id = Column(String, ForeignKey("chat_threads.thread_id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    message_order = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    thread = relationship("ChatThread", back_populates="messages")

    __table_args__ = (
        Index('ix_chat_messages_thread_id', 'thread_id'),
    )

# ===================== UPLOAD MODELS =====================
class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    thread_id = Column(String, ForeignKey("chat_threads.thread_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    extracted_data = Column(JSONB, nullable=True)
    extraction_status = Column(String, default='processing', nullable=False)
    extraction_error = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="invoices")
    thread = relationship("ChatThread", back_populates="invoices")

    __table_args__ = (
        Index('ix_invoices_thread_id', 'thread_id'),
        Index('ix_invoices_user_id', 'user_id'),
        Index('ix_invoices_extraction_status', 'extraction_status'),
    )

class Passport(Base):
    __tablename__ = "passports"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    thread_id = Column(String, ForeignKey("chat_threads.thread_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    extracted_data = Column(JSONB, nullable=True)
    extraction_status = Column(String, default='processing', nullable=False)
    extraction_error = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="passports")
    thread = relationship("ChatThread", back_populates="passports")

    __table_args__ = (
        Index('ix_passports_thread_id', 'thread_id'),
        Index('ix_passports_user_id', 'user_id'),
        Index('ix_passports_extraction_status', 'extraction_status'),
    )

class Visa(Base):
    __tablename__ = "visas"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    thread_id = Column(String, ForeignKey("chat_threads.thread_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    extracted_data = Column(JSONB, nullable=True)
    extraction_status = Column(String, default='processing', nullable=False)
    extraction_error = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="visas")
    thread = relationship("ChatThread", back_populates="visas")

    __table_args__ = (
        Index('ix_visas_thread_id', 'thread_id'),
        Index('ix_visas_user_id', 'user_id'),
        Index('ix_visas_extraction_status', 'extraction_status'),
    )
