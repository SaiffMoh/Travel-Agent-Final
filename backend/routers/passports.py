from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import os, uuid, shutil, logging
logger = logging.getLogger(__name__)
from pathlib import Path
from .. import schemas, crud
from ..database import get_db
from ..deps import get_current_active_user
from Utils.passport_decoder_json import process_passport_file_json
from Utils.passport_decoder import generate_passport_html

router = APIRouter(prefix="/api/v1/travel/passports", tags=["passports"])

UPLOAD_DIR = Path("data/uploads/passports")
MAX_FILES = 10
MAX_FILE_SIZE_MB = 2
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXT = {'pdf', 'jpg', 'jpeg', 'png', 'bmp', 'tiff'}

@router.post("/upload", response_class=HTMLResponse)
async def upload_passports(
    files: List[UploadFile] = File(...),
    thread_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    if len(files) > MAX_FILES:
        return "<div class='error'>Too many files. Max 10 allowed.</div>"
    if not files:
        return "<div class='error'>No files uploaded.</div>"
    # Ensure thread exists in DB
    thread = await crud.get_chat_thread(db, thread_id)
    if thread is None:
        thread = await crud.create_chat_thread(db, thread_id, user_id=current_user.id)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    html_blocks = []
    for file in files:
        ext = file.filename.split('.')[-1].lower()
        if ext not in ALLOWED_EXT:
            html_blocks.append(f"<div class='error'>Invalid file type: {file.filename}</div>")
            continue
        content = await file.read()
        if len(content) > MAX_FILE_SIZE_BYTES:
            html_blocks.append(f"<div class='error'>File too large: {file.filename}</div>")
            continue
        save_name = f"{uuid.uuid4()}_{file.filename}"
        save_path = UPLOAD_DIR / thread_id / save_name
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(content)
        db_passport = await crud.create_passport(db, schemas.PassportCreate(
            thread_id=thread_id,
            user_id=current_user.id,
            filename=file.filename,
            file_path=str(save_path),
            file_size=len(content)
        ))
        try:
            extracted = process_passport_file_json(str(save_path))
            logger.info(f"PASSPORT extracted for {file.filename}: {extracted}")
            # Normalize keys to match expected schema for DB and HTML
            normalized = {
                'full_name': extracted.get('full_name') or extracted.get('NameInPassport', ''),
                'surname': extracted.get('surname', ''),
                'given_names': extracted.get('given_names', ''),
                'passport_number': extracted.get('passport_number') or extracted.get('PassportNum', ''),
                'nationality': extracted.get('nationality', ''),
                'country_code': extracted.get('country_code', ''),
                'birth_date': extracted.get('birth_date', ''),
                'gender': extracted.get('gender', ''),
                'expiry_date': extracted.get('expiry_date') or extracted.get('ExpiryDate', ''),
                'issued_date': extracted.get('issued_date', ''),
                'passport_type': extracted.get('passport_type', ''),
            } if extracted and 'error' not in extracted else extracted
            await crud.update_passport_extraction(db, db_passport.id, normalized, status="completed")
            logger.info(f"PASSPORT saved to DB for {file.filename}, passport_id={db_passport.id}")
            html = generate_passport_html([normalized]) if normalized else "<div>Passport processed.</div>"
        except Exception as e:
            logger.error(f"PASSPORT extraction error for {file.filename}: {e}")
            await crud.update_passport_extraction(db, db_passport.id, {}, status="error", error=str(e))
            html = f"<div class='error'>Extraction failed: {str(e)}</div>"
        html_blocks.append(html)
    return "".join(html_blocks)

@router.get("/thread/{thread_id}", response_class=HTMLResponse)
async def get_passports_for_thread(thread_id: str, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_active_user)):
    passports = await crud.get_passports_for_thread(db, thread_id)
    html = "".join([f"<div>{p.filename} - {p.extraction_status}</div>" for p in passports])
    return html

@router.get("/{passport_id}", response_class=HTMLResponse)
async def get_passport(passport_id: int, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_active_user)):
    passport = await crud.get_passport(db, passport_id)
    if not passport:
        return "<div class='error'>Not found.</div>"
    # Defensive: if extracted_data is not normalized, normalize it for display
    data = passport.extracted_data
    if data and 'error' not in data:
        normalized = {
            'full_name': data.get('full_name') or data.get('NameInPassport', ''),
            'surname': data.get('surname', ''),
            'given_names': data.get('given_names', ''),
            'passport_number': data.get('passport_number') or data.get('PassportNum', ''),
            'nationality': data.get('nationality', ''),
            'country_code': data.get('country_code', ''),
            'birth_date': data.get('birth_date', ''),
            'gender': data.get('gender', ''),
            'expiry_date': data.get('expiry_date') or data.get('ExpiryDate', ''),
            'issued_date': data.get('issued_date', ''),
            'passport_type': data.get('passport_type', ''),
        }
        html = generate_passport_html([normalized])
    elif data:
        html = generate_passport_html([data])
    else:
        html = "<div>No data.</div>"
    return html

@router.delete("/{passport_id}", response_class=HTMLResponse)
async def delete_passport(passport_id: int, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_active_user)):
    passport = await crud.get_passport(db, passport_id)
    if not passport:
        return "<div class='error'>Not found.</div>"
    try:
        if os.path.exists(passport.file_path):
            os.remove(passport.file_path)
        await crud.delete_passport(db, passport_id)
        return "<div class='success'>Passport deleted.</div>"
    except Exception as e:
        return f"<div class='error'>Delete failed: {str(e)}</div>"

@router.post("/extract", response_class=HTMLResponse)
async def extract_passports(files: List[UploadFile] = File(...), thread_id: str = Form(...)):
    results = []
    for file in files:
        ext = file.filename.split('.')[-1].lower()
        if ext not in ALLOWED_EXT:
            results.append({"filename": file.filename, "error": "Invalid file type."})
            continue
        content = await file.read()
        if len(content) > MAX_FILE_SIZE_BYTES:
            results.append({"filename": file.filename, "error": "File too large."})
            continue
        temp_path = f"/tmp/{uuid.uuid4()}_{file.filename}"
        with open(temp_path, "wb") as f:
            f.write(content)
        try:
            extracted = process_passport_file_json(temp_path)
            results.append({"filename": file.filename, "extracted": extracted})
        except Exception as e:
            results.append({"filename": file.filename, "error": str(e)})
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    return {"results": results}
