from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

# User Schemas
class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserRead(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

# Auth Schemas
class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    success: bool
    token: str
    user: UserRead

class UserRegisterRequest(BaseModel):
    email: str
    password: str

class UserRegisterResponse(BaseModel):
    success: bool
    message: str
    user_id: int

class VerifyOTPRequest(BaseModel):
    email: str
    otp_code: str

class VerifyOTPResponse(BaseModel):
    success: bool
    message: str
    token: Optional[str] = None
    user: Optional[UserRead] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class MeResponse(BaseModel):
    user: UserRead
    loggedInAt: datetime

# Chat Schemas
class ChatMessageCreate(BaseModel):
    thread_id: str
    question: str
    response: str

class ChatMessageRead(BaseModel):
    id: int
    thread_id: str
    question: str
    response: str
    message_order: int
    created_at: datetime
    class Config:
        from_attributes = True


class ChatThreadResponse(BaseModel):
    thread_id: str
    messages: List[ChatMessageRead]

# ===================== UPLOAD SCHEMAS =====================
class InvoiceBase(BaseModel):
    thread_id: str
    user_id: int
    filename: str
    file_path: str
    file_size: int

class InvoiceCreate(InvoiceBase):
    pass

class InvoiceRead(InvoiceBase):
    id: int
    extracted_data: Optional[dict]
    extraction_status: str
    extraction_error: Optional[str]
    uploaded_at: datetime
    processed_at: Optional[datetime]
    class Config:
        from_attributes = True

class InvoiceUploadResponse(BaseModel):
    success: bool
    html: str
    invoice_id: int

class PassportBase(BaseModel):
    thread_id: str
    user_id: int
    filename: str
    file_path: str
    file_size: int

class PassportCreate(PassportBase):
    pass

class PassportRead(PassportBase):
    id: int
    extracted_data: Optional[dict]
    extraction_status: str
    extraction_error: Optional[str]
    uploaded_at: datetime
    processed_at: Optional[datetime]
    class Config:
        from_attributes = True

class PassportUploadResponse(BaseModel):
    success: bool
    html: str
    passport_id: int

class VisaBase(BaseModel):
    thread_id: str
    user_id: int
    filename: str
    file_path: str
    file_size: int

class VisaCreate(VisaBase):
    pass

class VisaRead(VisaBase):
    id: int
    extracted_data: Optional[dict]
    extraction_status: str
    extraction_error: Optional[str]
    uploaded_at: datetime
    processed_at: Optional[datetime]
    class Config:
        from_attributes = True

class VisaUploadResponse(BaseModel):
    success: bool
    html: str
    visa_id: int

class ChatThreadListItem(BaseModel):
    thread_id: str
    message_count: int
    created_at: datetime
    updated_at: datetime
