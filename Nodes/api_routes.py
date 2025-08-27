from fastapi import APIRouter, UploadFile, HTTPException, status
from pathlib import Path
import shutil
import uuid
import json
from Nodes.invoice_extraction_node import InvoiceExtractor

# Initialize router
router = APIRouter()

# Setup directories
UPLOAD_DIR = Path("uploads")
PDF_DIR = UPLOAD_DIR / "pdfs"
JSON_DIR = UPLOAD_DIR / "json_outputs"

# Create directories if they don't exist
for directory in [PDF_DIR, JSON_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

extractor = InvoiceExtractor()

@router.post("/api/invoices/upload")
async def upload_invoice(file: UploadFile):
    try:
        # Validate file type (PDF only)
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF files are supported"
            )
        
        # Generate unique filename
        filename = f"{uuid.uuid4()}.pdf"
        file_path = PDF_DIR / filename
        
        # Save uploaded PDF
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Process PDF
        text = extractor.extract_text_from_pdf(str(file_path))
        
        # Extract data
        invoice_data, raw_output = extractor.extract_invoice_data(text)
        if not invoice_data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "Failed to process invoice"}
            )
        
        # Convert Pydantic model to dict with datetime serialization
        def serialize_datetime(obj):
            from datetime import datetime
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
            
        invoice_dict = json.loads(invoice_data.json())
        
        # Save JSON output
        json_filename = f"{file_path.stem}.json"
        json_path = JSON_DIR / json_filename
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(invoice_dict, f, indent=2, ensure_ascii=False, default=serialize_datetime)
        
        return {
            "status": "success",
            "data": invoice_dict,
            "json_path": str(json_path.relative_to(UPLOAD_DIR))
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(e)}
        )
    finally:
        # Clean up the uploaded file
        if 'file_path' in locals() and file_path.exists():
            file_path.unlink()
