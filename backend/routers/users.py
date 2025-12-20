from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import secrets
from .. import schemas, crud
from ..database import get_db
from ..deps import get_current_active_user
from ..utils.send_email import send_otp_email

router = APIRouter(prefix="/api/v1/travel/users", tags=["users"])

@router.post("/register", response_model=schemas.UserRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: schemas.UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await crud.get_user_by_email(db, email=user_data.email.lower())
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user_create = schemas.UserCreate(email=user_data.email, password=user_data.password, name=None)
    new_user = await crud.create_user(db, user_create, is_active=False)
    otp_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    await crud.create_otp(db, new_user.email, otp_code, expires_at)
    send_otp_email(new_user.email, otp_code)
    return schemas.UserRegisterResponse(success=True, message="User registered successfully. Please check your email for OTP verification code.", user_id=new_user.id)

@router.post("/verify-otp", response_model=schemas.VerifyOTPResponse, status_code=status.HTTP_200_OK)
async def verify_otp(otp_data: schemas.VerifyOTPRequest, db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_email(db, email=otp_data.email.lower())
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already verified")
    otp = await crud.get_valid_otp(db, otp_data.email.lower(), otp_data.otp_code)
    if not otp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP code")
    await crud.mark_otp_as_used(db, otp.id)
    await crud.activate_user(db, user.id)
    await db.refresh(user)
    from ..security import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
    access_token_expires = timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    return schemas.VerifyOTPResponse(success=True, message="Email verified successfully. Your account has been activated.", token=access_token, user=schemas.UserRead(id=user.id, email=user.email, name=user.name, is_active=user.is_active, created_at=user.created_at, updated_at=user.updated_at))

@router.get("/me", response_model=schemas.UserRead)
async def read_own_profile(current_user = Depends(get_current_active_user)):
    return schemas.UserRead(id=current_user.id, email=current_user.email, name=current_user.name, is_active=current_user.is_active, created_at=current_user.created_at, updated_at=current_user.updated_at)
