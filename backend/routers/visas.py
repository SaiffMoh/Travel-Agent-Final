from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import os, uuid, shutil
from pathlib import Path
from .. import schemas, crud
from ..database import get_db
from ..deps import get_current_active_user
from Utils.visa_decoder import process_visa_file, generate_visa_html

router = APIRouter(prefix="/api/v1/travel/visas", tags=["visas"])

UPLOAD_DIR = Path("data/uploads/visas")
MAX_FILES = 10
MAX_FILE_SIZE_MB = 2
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXT = {'pdf', 'jpg', 'jpeg', 'png', 'bmp', 'tiff'}

@router.post("/upload", response_class=HTMLResponse)
async def upload_visas(
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
    elif thread.user_id is not None and thread.user_id != current_user.id:
        return "<div class='error'>Access denied.</div>"
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
        db_visa = await crud.create_visa(db, schemas.VisaCreate(
            thread_id=thread_id,
            user_id=current_user.id,
            filename=file.filename,
            file_path=str(save_path),
            file_size=len(content)
        ))
        try:
            extracted = process_visa_file(str(save_path))
            await crud.update_visa_extraction(db, db_visa.id, extracted, status="completed")
            html = generate_visa_html([extracted]) if extracted else "<div>Visa processed.</div>"
        except Exception as e:
            await crud.update_visa_extraction(db, db_visa.id, {}, status="error", error=str(e))
            html = f"<div class='error'>Extraction failed: {str(e)}</div>"
        html_blocks.append(html)
    return "".join(html_blocks)

@router.get("/thread/{thread_id}", response_class=HTMLResponse)
async def get_visas_for_thread(thread_id: str, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_active_user)):
    visas = await crud.get_visas_for_thread(db, thread_id)
    html = "".join([f"<div>{v.filename} - {v.extraction_status}</div>" for v in visas if v.user_id == current_user.id])
    return html

@router.get("/{visa_id}", response_class=HTMLResponse)
async def get_visa(visa_id: int, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_active_user)):
    visa = await crud.get_visa(db, visa_id)
    if not visa or visa.user_id != current_user.id:
        return "<div class='error'>Not found or access denied.</div>"
    html = generate_visa_html([visa.extracted_data]) if visa.extracted_data else "<div>No data.</div>"
    return html

@router.delete("/{visa_id}", response_class=HTMLResponse)
async def delete_visa(visa_id: int, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_active_user)):
    visa = await crud.get_visa(db, visa_id)
    if not visa or visa.user_id != current_user.id:
        return "<div class='error'>Not found or access denied.</div>"
    try:
        if os.path.exists(visa.file_path):
            os.remove(visa.file_path)
        await crud.delete_visa(db, visa_id)
        return "<div class='success'>Visa deleted.</div>"
    except Exception as e:
        return f"<div class='error'>Delete failed: {str(e)}</div>"

@router.post("/extract", response_class=HTMLResponse)
async def extract_visas(files: List[UploadFile] = File(...), thread_id: str = Form(...)):
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
            extracted = process_visa_file(temp_path)
            results.append({"filename": file.filename, "extracted": extracted})
        except Exception as e:
            results.append({"filename": file.filename, "error": str(e)})
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    return {"results": results}
