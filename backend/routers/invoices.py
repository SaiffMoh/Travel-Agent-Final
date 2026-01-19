from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import os, uuid, logging
from datetime import datetime
from pathlib import Path
from Utils.invoice_to_html import invoice_to_html
from graph import create_travel_graph
import asyncio, shutil
from ..database import get_db
from ..deps import get_current_active_user
from .. import schemas, crud

logger = logging.getLogger(__name__)
logging.getLogger('pdfminer.pdffont').setLevel(logging.ERROR)

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])

UPLOAD_DIR = Path("data/uploads/invoices")
MAX_FILES = 10
MAX_FILE_SIZE_MB = 2
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXT = {'pdf'}

def normalize_invoice_data(data):
    """Normalize invoice field names to standard format."""
    if not isinstance(data, dict):
        return data
    
    # Top-level field mapping
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
    
    # Flight field mapping
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


@router.post("/process", response_class=HTMLResponse)
async def process_invoices(
    files: List[UploadFile] = File(...),
    thread_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Single endpoint to upload and process invoice PDFs with database persistence.
    Returns structured HTML representation of extracted data.
    """
    # Validation
    if not files:
        return '<div class="p-4 bg-red-50 border border-red-200 rounded-lg"><p class="text-red-600">No files uploaded.</p></div>'
    
    if len(files) > MAX_FILES:
        return f'<div class="p-4 bg-red-50 border border-red-200 rounded-lg"><p class="text-red-600">Too many files. Maximum {MAX_FILES} allowed.</p></div>'
    
    # Ensure thread exists in DB
    thread = await crud.get_chat_thread(db, thread_id)
    if thread is None:
        thread = await crud.create_chat_thread(db, thread_id, user_id=current_user.id)
    elif thread.user_id is not None and thread.user_id != current_user.id:
        return '<div class="p-4 bg-red-50 border border-red-200 rounded-lg"><p class="text-red-600">Access denied.</p></div>'
    
    # Ensure upload directory exists
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    # Compile graph once for this request
    graph = create_travel_graph().compile()

    html_blocks = []
    
    for file in files:
        # Validate file extension
        ext = file.filename.split('.')[-1].lower() if file.filename else ''
        if ext not in ALLOWED_EXT:
            html_blocks.append(
                f'<div class="p-4 mb-4 bg-yellow-50 border border-yellow-200 rounded-lg">'
                f'<p class="text-yellow-700"><strong>{file.filename}</strong>: Invalid file type. Only PDF files are allowed.</p>'
                f'</div>'
            )
            continue
        
        # Read and validate file size
        content = await file.read()
        if len(content) > MAX_FILE_SIZE_BYTES:
            html_blocks.append(
                f'<div class="p-4 mb-4 bg-yellow-50 border border-yellow-200 rounded-lg">'
                f'<p class="text-yellow-700"><strong>{file.filename}</strong>: File too large. Maximum {MAX_FILE_SIZE_MB}MB allowed.</p>'
                f'</div>'
            )
            continue
        
        # Save file to disk under data/uploads/invoice_pdfs/<thread_id>
        save_name = f"{uuid.uuid4()}_{file.filename}"
        invoice_pdf_dir = Path("data/uploads/invoice_pdfs") / thread_id
        invoice_pdf_dir.mkdir(parents=True, exist_ok=True)
        save_path = invoice_pdf_dir / save_name

        try:
            with open(save_path, "wb") as f:
                f.write(content)

            # Create invoice record in database (persist before processing)
            db_invoice = await crud.create_invoice(db, schemas.InvoiceCreate(
                thread_id=thread_id,
                user_id=current_user.id,
                filename=file.filename,
                file_path=str(save_path),
                file_size=len(content)
            ))

            # Prepare state for graph-driven invoice extraction
            state = {
                "thread_id": thread_id,
                "current_message": f"Processing uploaded invoice: {file.filename}",
                "user_message": f"Processing uploaded invoice: {file.filename}",
                "needs_followup": True,
                "followup_question": None,
                "current_node": "invoice_extraction",
                "invoice_uploaded": True,
                "invoice_pdf_path": str(save_path),
                "extracted_invoice_data": None,
                "invoice_html": None
            }

            try:
                try:
                    state["main_event_loop"] = asyncio.get_running_loop()
                except RuntimeError:
                    state["main_event_loop"] = None

                # Run graph to extract invoice HTML and data
                result = await graph.ainvoke(state)

                invoice_html = result.get("invoice_html", f"""
                <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                    <p class="text-yellow-600">Invoice '{file.filename}' processed but no data extracted.</p>
                </div>
                """)

                # Normalize and persist extracted data
                extracted = result.get("extracted_invoice_data")
                normalized = normalize_invoice_data(extracted) if extracted else {}

                await crud.update_invoice_extraction(
                    db,
                    db_invoice.id,
                    normalized,
                    status="completed"
                )

                # Persist conversation state so subsequent messages continue in same thread
                await crud.save_conversation_state(db, thread_id, {
                    "invoice_uploaded": True,
                    "invoice_pdf_path": str(save_path),
                    "extracted_invoice_data": normalized,
                    "invoice_html": invoice_html,
                    "last_action": "invoice_upload",
                    "last_action_timestamp": datetime.now().isoformat()
                })

                # CRITICAL: Save message to chat history so the thread persists
                await crud.create_chat_message(
                    db,
                    thread_id=thread_id,
                    question=f"Uploaded invoice: {file.filename}",
                    response=invoice_html
                )

                # Add file header if multiple files
                if len(files) > 1:
                    html_blocks.append(f"""
                    <div class="mb-6">
                        <h3 class="text-lg font-semibold text-gray-800 mb-3">File: {file.filename}</h3>
                        {invoice_html}
                    </div>
                    """)
                else:
                    html_blocks.append(invoice_html)

            except Exception as node_exc:
                logger.error(f"Graph extraction error for {file.filename}: {node_exc}")
                # Update DB with error state
                await crud.update_invoice_extraction(
                    db,
                    db_invoice.id,
                    {},
                    status="error",
                    error=str(node_exc)
                )
                html_blocks.append(f"""
                <div class="p-4 bg-red-50 border border-red-200 rounded-lg mb-4">
                    <p class="text-red-600">Error processing '{file.filename}': {str(node_exc)}</p>
                </div>
                """)

        except Exception as e:
            logger.error(f"Error saving/processing {file.filename}: {str(e)}")
            # Update invoice with error status in database if record was created
            if 'db_invoice' in locals():
                await crud.update_invoice_extraction(
                    db,
                    db_invoice.id,
                    {},
                    status="error",
                    error=str(e)
                )
            html_blocks.append(f"""
            <div class="p-4 mb-4 bg-red-50 border border-red-200 rounded-lg">
                <p class="text-red-600"><strong>{file.filename}</strong>: Processing failed - {str(e)}</p>
            </div>
            """)
    
    return "".join(html_blocks)


@router.get("/thread/{thread_id}", response_class=HTMLResponse)
async def get_invoices_for_thread(
    thread_id: str, 
    db: AsyncSession = Depends(get_db), 
    current_user = Depends(get_current_active_user)
):
    """Get all invoices for a specific thread."""
    invoices = await crud.get_invoices_for_thread(db, thread_id)
    
    if not invoices:
        return '<div class="p-4 text-muted-foreground">No invoices found for this thread.</div>'
    
    html_blocks = []
    for inv in invoices:
        if inv.user_id != current_user.id:
            continue
            
        status_color = {
            'completed': 'green',
            'processing': 'blue',
            'error': 'red',
            'pending': 'yellow'
        }.get(inv.extraction_status, 'gray')
        
        html_blocks.append(
            f'<div class="p-3 mb-2 bg-{status_color}-50 border border-{status_color}-200 rounded-lg">'
            f'<div class="font-semibold">{inv.filename}</div>'
            f'<div class="text-sm text-{status_color}-600">Status: {inv.extraction_status}</div>'
            f'<div class="text-xs text-muted-foreground">{inv.uploaded_at.strftime("%Y-%m-%d %H:%M")}</div>'
            f'</div>'
        )
    
    return "".join(html_blocks)


@router.get("/{invoice_id}", response_class=HTMLResponse)
async def get_invoice(
    invoice_id: int, 
    db: AsyncSession = Depends(get_db), 
    current_user = Depends(get_current_active_user)
):
    """Get a specific invoice by ID."""
    invoice = await crud.get_invoice(db, invoice_id)
    
    if not invoice or invoice.user_id != current_user.id:
        return '<div class="p-4 bg-red-50 border border-red-200 rounded-lg"><p class="text-red-600">Invoice not found or access denied.</p></div>'
    
    if not invoice.extracted_data:
        return '<div class="p-4 text-muted-foreground">No extracted data available.</div>'
    
    # Normalize before rendering
    normalized = normalize_invoice_data(invoice.extracted_data)
    html = invoice_to_html(normalized)
    
    # Add filename header
    return (
        f'<div class="mb-6">'
        f'<div class="bg-blue-100 border-l-4 border-blue-500 p-3 mb-2">'
        f'<h3 class="text-lg font-semibold text-blue-900">📄 {invoice.filename}</h3>'
        f'<div class="text-sm text-blue-600">Uploaded: {invoice.uploaded_at.strftime("%Y-%m-%d %H:%M")}</div>'
        f'</div>'
        f'{html}'
        f'</div>'
    )


@router.delete("/{invoice_id}", response_class=HTMLResponse)
async def delete_invoice(
    invoice_id: int, 
    db: AsyncSession = Depends(get_db), 
    current_user = Depends(get_current_active_user)
):
    """Delete a specific invoice."""
    invoice = await crud.get_invoice(db, invoice_id)
    
    if not invoice or invoice.user_id != current_user.id:
        return '<div class="p-4 bg-red-50 border border-red-200 rounded-lg"><p class="text-red-600">Invoice not found or access denied.</p></div>'
    
    try:
        # Delete file from disk if it exists
        if os.path.exists(invoice.file_path):
            os.remove(invoice.file_path)
        
        # Delete from database
        await crud.delete_invoice(db, invoice_id)
        
        return '<div class="p-4 bg-green-50 border border-green-200 rounded-lg"><p class="text-green-600">Invoice deleted successfully.</p></div>'
    except Exception as e:
        logger.error(f"Error deleting invoice {invoice_id}: {str(e)}")
        return f'<div class="p-4 bg-red-50 border border-red-200 rounded-lg"><p class="text-red-600">Delete failed: {str(e)}</p></div>'