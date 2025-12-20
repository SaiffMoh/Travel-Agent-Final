from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List
from datetime import datetime
from . import models, schemas
from .security import get_password_hash
import uuid

# User CRUD
async def get_user_by_email(db: AsyncSession, email: str) -> Optional[models.User]:
    result = await db.execute(select(models.User).where(models.User.email == email.lower()))
    return result.scalar_one_or_none()

async def get_user(db: AsyncSession, user_id: int) -> Optional[models.User]:
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, user: schemas.UserCreate, is_active: bool = False) -> models.User:
    name = user.name if user.name else user.email.split("@")[0]
    db_user = models.User(
        email=user.email.lower(),
        hashed_password=get_password_hash(user.password),
        name=name,
        is_active=is_active
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def activate_user(db: AsyncSession, user_id: int) -> bool:
    user = await get_user(db, user_id)
    if user:
        user.is_active = True
        await db.commit()
        await db.refresh(user)
        return True
    return False

# OTP CRUD
async def create_otp(db: AsyncSession, email: str, otp_code: str, expires_at) -> models.EmailOTP:
    db_otp = models.EmailOTP(
        email=email.lower(),
        otp_code=otp_code,
        expires_at=expires_at,
        is_used=False
    )
    db.add(db_otp)
    await db.commit()
    await db.refresh(db_otp)
    return db_otp

async def get_valid_otp(db: AsyncSession, email: str, otp_code: str) -> Optional[models.EmailOTP]:
    result = await db.execute(
        select(models.EmailOTP)
        .where(
            models.EmailOTP.email == email.lower(),
            models.EmailOTP.otp_code == otp_code,
            models.EmailOTP.is_used == False,
            models.EmailOTP.expires_at > datetime.utcnow()
        )
        .order_by(models.EmailOTP.created_at.desc())
    )
    return result.scalar_one_or_none()

async def mark_otp_as_used(db: AsyncSession, otp_id: int) -> bool:
    result = await db.execute(select(models.EmailOTP).where(models.EmailOTP.id == otp_id))
    otp = result.scalar_one_or_none()
    if otp:
        otp.is_used = True
        await db.commit()
        return True
    return False


# ===================== UPLOAD CRUD =====================
## INVOICE CRUD
async def create_invoice(db: AsyncSession, invoice: schemas.InvoiceCreate) -> models.Invoice:
    db_invoice = models.Invoice(**invoice.dict())
    db.add(db_invoice)
    await db.commit()
    await db.refresh(db_invoice)
    return db_invoice

async def get_invoice(db: AsyncSession, invoice_id: int) -> Optional[models.Invoice]:
    result = await db.execute(select(models.Invoice).where(models.Invoice.id == invoice_id))
    return result.scalar_one_or_none()

async def get_invoices_for_thread(db: AsyncSession, thread_id: str) -> List[models.Invoice]:
    result = await db.execute(select(models.Invoice).where(models.Invoice.thread_id == thread_id))
    return list(result.scalars().all())

async def update_invoice_extraction(db: AsyncSession, invoice_id: int, extracted_data: dict, status: str = 'completed', error: Optional[str] = None):
    invoice = await get_invoice(db, invoice_id)
    if invoice:
        invoice.extracted_data = extracted_data
        invoice.extraction_status = status
        invoice.extraction_error = error
        invoice.processed_at = datetime.utcnow()
        await db.commit()
        await db.refresh(invoice)
    return invoice

async def delete_invoice(db: AsyncSession, invoice_id: int) -> bool:
    invoice = await get_invoice(db, invoice_id)
    if invoice:
        await db.delete(invoice)
        await db.commit()
        return True
    return False

## PASSPORT CRUD
async def create_passport(db: AsyncSession, passport: schemas.PassportCreate) -> models.Passport:
    db_passport = models.Passport(**passport.dict())
    db.add(db_passport)
    await db.commit()
    await db.refresh(db_passport)
    return db_passport

async def get_passport(db: AsyncSession, passport_id: int) -> Optional[models.Passport]:
    result = await db.execute(select(models.Passport).where(models.Passport.id == passport_id))
    return result.scalar_one_or_none()

async def get_passports_for_thread(db: AsyncSession, thread_id: str) -> List[models.Passport]:
    result = await db.execute(select(models.Passport).where(models.Passport.thread_id == thread_id))
    return list(result.scalars().all())

async def update_passport_extraction(db: AsyncSession, passport_id: int, extracted_data: dict, status: str = 'completed', error: Optional[str] = None):
    passport = await get_passport(db, passport_id)
    if passport:
        passport.extracted_data = extracted_data
        passport.extraction_status = status
        passport.extraction_error = error
        passport.processed_at = datetime.utcnow()
        await db.commit()
        await db.refresh(passport)
    return passport

async def delete_passport(db: AsyncSession, passport_id: int) -> bool:
    passport = await get_passport(db, passport_id)
    if passport:
        await db.delete(passport)
        await db.commit()
        return True
    return False

## VISA CRUD
async def create_visa(db: AsyncSession, visa: schemas.VisaCreate) -> models.Visa:
    db_visa = models.Visa(**visa.dict())
    db.add(db_visa)
    await db.commit()
    await db.refresh(db_visa)
    return db_visa

async def get_visa(db: AsyncSession, visa_id: int) -> Optional[models.Visa]:
    result = await db.execute(select(models.Visa).where(models.Visa.id == visa_id))
    return result.scalar_one_or_none()

async def get_visas_for_thread(db: AsyncSession, thread_id: str) -> List[models.Visa]:
    result = await db.execute(select(models.Visa).where(models.Visa.thread_id == thread_id))
    return list(result.scalars().all())

async def update_visa_extraction(db: AsyncSession, visa_id: int, extracted_data: dict, status: str = 'completed', error: Optional[str] = None):
    visa = await get_visa(db, visa_id)
    if visa:
        visa.extracted_data = extracted_data
        visa.extraction_status = status
        visa.extraction_error = error
        visa.processed_at = datetime.utcnow()
        await db.commit()
        await db.refresh(visa)
    return visa

async def delete_visa(db: AsyncSession, visa_id: int) -> bool:
    visa = await get_visa(db, visa_id)
    if visa:
        await db.delete(visa)
        await db.commit()
        return True
    return False

async def get_chat_threads_for_user(db: AsyncSession, user_id: int) -> List[models.ChatThread]:
    result = await db.execute(select(models.ChatThread).where(
        (models.ChatThread.user_id == user_id) | (models.ChatThread.user_id.is_(None))
    ))
    return list(result.scalars().all())

async def create_chat_thread(db: AsyncSession, thread_id: str, user_id: Optional[int] = None) -> models.ChatThread:
    db_thread = models.ChatThread(thread_id=thread_id, user_id=user_id)
    db.add(db_thread)
    await db.commit()
    await db.refresh(db_thread)
    return db_thread

async def generate_unique_thread_id(db: AsyncSession) -> str:
    # Generate a UUID and ensure it's unique
    while True:
        thread_id = str(uuid.uuid4())
        exists = await get_chat_thread(db, thread_id)
        if not exists:
            return thread_id

async def get_chat_thread(db: AsyncSession, thread_id: str) -> Optional[models.ChatThread]:
    result = await db.execute(select(models.ChatThread).where(models.ChatThread.thread_id == thread_id))
    return result.scalar_one_or_none()

# Chat Message CRUD
async def get_message_count_for_thread(db: AsyncSession, thread_id: str) -> int:
    result = await db.execute(select(func.count(models.ChatMessage.id)).where(models.ChatMessage.thread_id == thread_id))
    return result.scalar() or 0

async def create_chat_message(db: AsyncSession, thread_id: str, question: str, response: str) -> models.ChatMessage:
    message_order = await get_message_count_for_thread(db, thread_id) + 1
    db_message = models.ChatMessage(
        thread_id=thread_id,
        question=question,
        response=response,
        message_order=message_order
    )
    db.add(db_message)
    await db.commit()
    await db.refresh(db_message)
    return db_message

async def get_messages_for_thread(db: AsyncSession, thread_id: str) -> List[models.ChatMessage]:
    result = await db.execute(select(models.ChatMessage).where(models.ChatMessage.thread_id == thread_id).order_by(models.ChatMessage.message_order))
    return list(result.scalars().all())

# Conversation State CRUD (for chat thread state persistence)
async def get_conversation_state(db: AsyncSession, thread_id: str) -> Optional[dict]:
    result = await db.execute(select(models.ChatThread).where(models.ChatThread.thread_id == thread_id))
    thread = result.scalar_one_or_none()
    if thread and hasattr(thread, 'state'):
        return thread.state or {}
    return {}

async def save_conversation_state(db: AsyncSession, thread_id: str, state: dict):
    result = await db.execute(select(models.ChatThread).where(models.ChatThread.thread_id == thread_id))
    thread = result.scalar_one_or_none()
    if thread:
        thread.state = state
        await db.commit()
        await db.refresh(thread)
    return thread
