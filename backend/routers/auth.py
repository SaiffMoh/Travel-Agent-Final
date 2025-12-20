from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from .. import schemas, crud
from ..database import get_db
from ..security import verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from ..deps import get_current_active_user

router = APIRouter(prefix="/api/v1/travel/auth", tags=["auth"])

@router.post("/login", response_model=schemas.LoginResponse, status_code=status.HTTP_200_OK)
async def login(login_data: schemas.LoginRequest, db: AsyncSession = Depends(get_db)):
    if not login_data.email or not login_data.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email and password are required")
    user = await crud.get_user_by_email(db, email=login_data.email.lower())
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account not verified. Please verify your email address.")
    access_token_expires = timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    return schemas.LoginResponse(success=True, token=access_token, user=schemas.UserRead(id=user.id, email=user.email, name=user.name, is_active=user.is_active, created_at=user.created_at, updated_at=user.updated_at))

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(current_user = Depends(get_current_active_user)):
    return {"success": True}

@router.get("/me", response_model=schemas.MeResponse, status_code=status.HTTP_200_OK)
async def get_current_user_info(current_user = Depends(get_current_active_user)):
    return schemas.MeResponse(user=schemas.UserRead(id=current_user.id, email=current_user.email, name=current_user.name, is_active=current_user.is_active, created_at=current_user.created_at, updated_at=current_user.updated_at), loggedInAt=datetime.utcnow())
