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

def process_single_pdf(file: UploadFile) -> dict:
    """Process a single PDF file and return the result."""
    temp_file_path = None
    try:
        # Validate file type (PDF only)
        if not file.filename.lower().endswith('.pdf'):
            return {
                "filename": file.filename,
                "status": "error",
                "error": "Only PDF files are supported"
            }
        
        # Generate unique filename
        filename = f"{uuid.uuid4()}.pdf"
        temp_file_path = PDF_DIR / filename
        
        # Save uploaded PDF
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Process PDF
        text = extractor.extract_text_from_pdf(str(temp_file_path))
        
        # Extract data
        invoice_data, raw_output = extractor.extract_invoice_data(text)
        if not invoice_data:
            return {
                "filename": file.filename,
                "status": "error",
                "error": "Failed to extract data from PDF"
            }
        
        # Convert Pydantic model to dict with datetime serialization
        def serialize_datetime(obj):
            from datetime import datetime
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
            
        invoice_dict = json.loads(invoice_data.json())
        
        # Save JSON output
        json_filename = f"{temp_file_path.stem}.json"
        json_path = JSON_DIR / json_filename
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(invoice_dict, f, indent=2, ensure_ascii=False, default=serialize_datetime)
        
        return {
            "filename": file.filename,
            "status": "success",
            "data": invoice_dict,
            "json_path": str(json_path.relative_to(UPLOAD_DIR))
        }
        
    except Exception as e:
        return {
            "filename": file.filename,
            "status": "error",
            "error": str(e)
        }
    finally:
        # Clean up the temporary uploaded file
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()

@router.post("/api/invoices/upload")
async def upload_invoice(files: list[UploadFile]):
    """
    Handle multiple PDF uploads.
    
    Args:
        files: List of PDF files to process
        
    Returns:
        List of processing results for each file
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )
    
    # Process each file sequentially
    results = []
    for file in files:
        result = process_single_pdf(file)
        results.append(result)
    
    # Check if all files failed
    if all(r["status"] == "error" for r in results):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Failed to process all files",
                "results": results
            }
        )
    
    return {
        "status": "success",
        "processed_count": len([r for r in results if r["status"] == "success"]),
        "error_count": len([r for r in results if r["status"] == "error"]),
        "results": results
    }
