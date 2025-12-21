from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from Nodes.invoice_extraction_node import generate_invoice_html
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import os, uuid, shutil, logging
logger = logging.getLogger(__name__)
# Reduce noisy pdfminer font warnings about missing FontBBox
logging.getLogger('pdfminer.pdffont').setLevel(logging.ERROR)
from pathlib import Path
from .. import schemas, crud
from ..database import get_db
from ..deps import get_current_active_user
from Nodes.invoice_extraction_json import invoice_extraction_json
from Models.ConversationStore import conversation_store

router = APIRouter(prefix="/api/v1/travel/invoices", tags=["invoices"])

UPLOAD_DIR = Path("data/uploads/invoices")
MAX_FILES = 10
MAX_FILE_SIZE_MB = 2
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXT = {'pdf'}

@router.post("/upload", response_class=HTMLResponse)
async def upload_invoices(
    files: List[UploadFile] = File(...),
    thread_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    if len(files) > MAX_FILES:
        return "<div class='error'>Too many files. Max 10 allowed.</div>"
    if not files:
        return "<div class='error'>No files uploaded.</div>"
    # Record upload action in conversation store (preserve legacy behavior)
    try:
        conversation_store.add_message(thread_id, "user", f"Uploaded {len(files)} invoice file(s)")
    except Exception:
        # non-fatal: conversation store may not be available in some contexts
        pass
    # Ensure thread exists in DB
    thread = await crud.get_chat_thread(db, thread_id)
    if thread is None:
        thread = await crud.create_chat_thread(db, thread_id, user_id=current_user.id)
    elif thread.user_id is not None and thread.user_id != current_user.id:
        return "<div class='error'>Access denied.</div>"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    html_blocks = []
    saved_paths = []
    extracted_list = []
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
        saved_paths.append(str(save_path))
        db_invoice = await crud.create_invoice(db, schemas.InvoiceCreate(
            thread_id=thread_id,
            user_id=current_user.id,
            filename=file.filename,
            file_path=str(save_path),
            file_size=len(content)
        ))
        try:
            extracted = invoice_extraction_json(str(save_path), thread_id)
            logger.info(f"INVOICE extracted for {file.filename}: {extracted}")

            # --- Normalization step: map extracted invoice data to legacy field names/structure ---
            def normalize_invoice_data(data):
                if not isinstance(data, dict):
                    return data
                # mapping with common alternative keys (case-insensitive)
                mapping = {
                    "invoicenumber": "invoice_number",
                    "invoicedate": "issued_date",
                    "submissiondate": "submission_date",
                    "vendortype": "vendor_type",
                    "vendorname": "vendor_name",
                    "subsidiaryname": "subsidiary_name",
                    "invoicestate": "invoice_state",
                    "currency": "currency",
                    "travelagency": "travel_agency",
                    "flight": "flight_details",
                    "totalamount": "total_amount",
                    "srreferencenumber": "invoice_number",
                    "cost": "total_amount",
                }

                # normalized flight field mapping (case-insensitive, common synonyms)
                flight_map = {
                    "date": "departure_date",
                    "departure": "origin",
                    "arrival": "destination",
                    "destination": "destination",
                    "price": "amount",
                    "cost": "amount",
                    "airline": "airline",
                    "passenger": "passenger",
                    "ticketnumber": "ticket_number",
                    "ticket_number": "ticket_number",
                    "servicetype": "service_type",
                    "tax": "tax",
                    "totalamount": "total_amount",
                    "returndate": "return_date",
                    "returndate": "return_date",
                }

                def normalize_field_name(k: str):
                    if not isinstance(k, str):
                        return k
                    key = k.replace(' ', '').replace('_', '').lower()
                    return mapping.get(key, key)

                normalized = {}
                for k, v in data.items():
                    key = normalize_field_name(k)
                    if key == "flight_details" and isinstance(v, list):
                        normalized[key] = []
                        for f in v:
                            if isinstance(f, dict):
                                norm_f = {}
                                for fk, fv in f.items():
                                    fk_norm = fk.replace(' ', '').replace('_', '').lower()
                                    mapped = flight_map.get(fk_norm, fk_norm)
                                    norm_f[mapped] = fv
                                normalized[key].append(norm_f)
                            else:
                                normalized[key].append(f)
                    else:
                        normalized[key] = v
                return normalized

            normalized = normalize_invoice_data(extracted)
            extracted_list.append(normalized)
            await crud.update_invoice_extraction(db, db_invoice.id, normalized, status="completed")
            logger.info(f"INVOICE saved to DB for {file.filename}, invoice_id={db_invoice.id}")
            from Utils.invoice_to_html import invoice_to_html
            html = invoice_to_html(normalized)
        except Exception as e:
            logger.error(f"INVOICE extraction error for {file.filename}: {e}")
            await crud.update_invoice_extraction(db, db_invoice.id, {}, status="error", error=str(e))
            html = f"<div class='error'>Extraction failed: {str(e)}</div>"
        html_blocks.append(html)
    # Save invoice-related state to conversation store (preserve travel_packages)
    try:
        current_state = conversation_store.get_state(thread_id) or {}
        state_to_save = {
            "invoice_uploaded": True,
            "invoice_pdf_paths": saved_paths,
            "extracted_invoice_data": extracted_list,
            "invoice_html": "".join(html_blocks),
            "travel_packages": current_state.get("travel_packages", []),
            "travel_packages_html": current_state.get("travel_packages_html"),
        }
        conversation_store.save_state(thread_id, state_to_save)
        conversation_store.add_message(thread_id, "assistant", "Invoice(s) processed")
    except Exception:
        pass
    return "".join(html_blocks)

@router.get("/thread/{thread_id}", response_class=HTMLResponse)
async def get_invoices_for_thread(thread_id: str, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_active_user)):
    invoices = await crud.get_invoices_for_thread(db, thread_id)
    html = "".join([f"<div>{inv.filename} - {inv.extraction_status}</div>" for inv in invoices if inv.user_id == current_user.id])
    return html

@router.get("/{invoice_id}", response_class=HTMLResponse)
async def get_invoice(invoice_id: int, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_active_user)):
    invoice = await crud.get_invoice(db, invoice_id)
    if not invoice or invoice.user_id != current_user.id:
        return "<div class='error'>Not found or access denied.</div>"
    if invoice.extracted_data:
        # Normalize before rendering
        def normalize_invoice_data(data):
            if not isinstance(data, dict):
                return data
            mapping = {
                "invoicenumber": "invoice_number",
                "invoicedate": "issued_date",
                "submissiondate": "submission_date",
                "vendortype": "vendor_type",
                "vendorname": "vendor_name",
                "subsidiaryname": "subsidiary_name",
                "invoicestate": "invoice_state",
                "currency": "currency",
                "travelagency": "travel_agency",
                "flight": "flight_details",
                "totalamount": "total_amount",
                "srreferencenumber": "invoice_number",
                "cost": "total_amount",
            }

            flight_map = {
                "date": "departure_date",
                "departure": "origin",
                "arrival": "destination",
                "destination": "destination",
                "price": "amount",
                "cost": "amount",
                "airline": "airline",
                "passenger": "passenger",
                "ticketnumber": "ticket_number",
                "ticket_number": "ticket_number",
                "servicetype": "service_type",
                "tax": "tax",
                "totalamount": "total_amount",
                "returndate": "return_date",
            }

            def normalize_field_name(k: str):
                if not isinstance(k, str):
                    return k
                key = k.replace(' ', '').replace('_', '').lower()
                return mapping.get(key, key)

            normalized = {}
            for k, v in data.items():
                key = normalize_field_name(k)
                if key == "flight_details" and isinstance(v, list):
                    normalized[key] = []
                    for f in v:
                        if isinstance(f, dict):
                            norm_f = {}
                            for fk, fv in f.items():
                                fk_norm = fk.replace(' ', '').replace('_', '').lower()
                                mapped = flight_map.get(fk_norm, fk_norm)
                                norm_f[mapped] = fv
                            normalized[key].append(norm_f)
                        else:
                            normalized[key].append(f)
                else:
                    normalized[key] = v
            return normalized
        from Utils.invoice_to_html import invoice_to_html
        html = invoice_to_html(normalize_invoice_data(invoice.extracted_data))
    else:
        html = "<div>No data.</div>"
    return html

@router.delete("/{invoice_id}", response_class=HTMLResponse)
async def delete_invoice(invoice_id: int, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_active_user)):
    invoice = await crud.get_invoice(db, invoice_id)
    if not invoice or invoice.user_id != current_user.id:
        return "<div class='error'>Not found or access denied.</div>"
    try:
        if os.path.exists(invoice.file_path):
            os.remove(invoice.file_path)
        await crud.delete_invoice(db, invoice_id)
        return "<div class='success'>Invoice deleted.</div>"
    except Exception as e:
        return f"<div class='error'>Delete failed: {str(e)}</div>"

@router.post("/extract", response_class=HTMLResponse)
async def extract_invoices(files: List[UploadFile] = File(...), thread_id: str = Form(...)):
    # Just run extraction and return JSON (no DB)
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
            extracted = invoice_extraction_json(temp_path)
            results.append({"filename": file.filename, "extracted": extracted})
        except Exception as e:
            results.append({"filename": file.filename, "error": str(e)})
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    return {"results": results}

from fastapi.responses import JSONResponse
@router.get("/json/{invoice_id}", response_class=JSONResponse)
async def get_invoice_json(invoice_id: int, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_active_user)):
    invoice = await crud.get_invoice(db, invoice_id)
    if not invoice or invoice.user_id != current_user.id:
        return JSONResponse(content={"error": "Not found or access denied."}, status_code=404)
    return JSONResponse(content=invoice.extracted_data or {})