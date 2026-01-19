import os
import traceback
import zxingcpp
import re
import datetime
import cv2
import numpy as np
import logging
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import tempfile
from Utils.ocr_engine import ocr_passport
import io
from PIL import Image
from Models.PassportModels import PassportData
 
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

 
def get_lower_left(image):
    """Extract the lower left quadrant where MRZ is typically located"""
    height, width = image.shape[:2]
    return image[height // 2:, :width // 2]
 
 
def detect_barcode(image):
    """
    Detect and crop barcode/MRZ region from passport image.
    Enhanced version with improved MRZ detection for horizontal text patterns.
    """
    original = image.copy()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
 
    gradX = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
    gradY = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=0, dy=1, ksize=-1)
    gradient = cv2.magnitude(gradX, gradY)
    gradient = cv2.convertScaleAbs(gradient)
 
    blurred = cv2.blur(gradient, (5, 5))
    _, thresh = cv2.threshold(blurred, 50, 255, cv2.THRESH_BINARY)
 
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
 
    closed = cv2.erode(closed, None, iterations=2)
    closed = cv2.dilate(closed, None, iterations=2)
 
    cnts, _ = cv2.findContours(closed.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        c = sorted(cnts, key=cv2.contourArea, reverse=True)[0]
        x, y, w, h = cv2.boundingRect(c)
 
        margin_x = int(w * 0.01)
        margin_y = int(h * 0.8)
        x_exp = max(x - margin_x, 0)
        y_exp = max(y - margin_y, 0)
        w_exp = min(w + 2 * margin_x, original.shape[1] - x_exp)
        h_exp = min(h + 2 * margin_y, original.shape[0] - y_exp)
 
        cropped = original[y_exp:y_exp + h_exp, x_exp:x_exp + w_exp]
        return cropped
 
    logger.warning("No barcode region detected, returning original image")
    return original
 
 
def format_date(s: str) -> str:
    """Format MRZ date string (YYMMDD) to ISO format (YYYY-MM-DD)"""
    yy = int(s[0:2])
    mm = int(s[2:4])
    dd = int(s[4:6])
   
    if yy <= 50:
        year = 2000 + yy
    else:
        year = 1900 + yy
   
    return f"{year:04d}-{mm:02d}-{dd:02d}"
 
 
def extract_passport_with_llm(ocr_text: str) -> dict:
    """
    Extract passport information using LLM when MRZ parsing fails.
    Falls back to manual text extraction from OCR output.
    
    Args:
        ocr_text: Raw OCR extracted text from passport image
        
    Returns:
        Dictionary with extracted passport fields or error
    """
    try:
        from Utils.getLLM import get_llm
        
        llm = get_llm()
        
        prompt = f"""Extract passport information from the following OCR text. Return ONLY a valid JSON object.

OCR Text:
{ocr_text}

Extract these fields:
- full_name: Full name of passport holder
- surname: Last name/family name
- given_names: First and middle names
- passport_number: Passport number (usually starts with a letter followed by 7-9 digits)
- nationality: 3-letter country code (e.g., EGY, USA, GBR)
- country_code: Same as nationality
- gender: M or F
- birth_date: Date of birth in YYYY-MM-DD format
- expiry_date: Passport expiry date in YYYY-MM-DD format
- passport_type: Usually 'P' for regular passport

RETURN ONLY THIS JSON (no markdown, no explanation):
{{
  "full_name": "",
  "surname": "",
  "given_names": "",
  "passport_number": "",
  "nationality": "",
  "country_code": "",
  "gender": "",
  "birth_date": "",
  "expiry_date": "",
  "passport_type": ""
}}"""
        
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Clean markdown code blocks if present
        response_text = response_text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        # Parse JSON
        import json
        extracted = json.loads(response_text)
        
        # Add metadata
        extracted['extraction_method'] = 'LLM_fallback'
        
        # Validate with Pydantic
        try:
            validated = PassportData(**extracted)
            logger.info(f"✓ LLM extracted and validated: {validated.full_name}, Passport: {validated.passport_number}")
            return validated.model_dump(by_alias=False, exclude_none=True)
        except Exception as validation_error:
            logger.warning(f"LLM extraction validation warning: {validation_error}")
            return extracted
        
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return {"error": f"LLM extraction failed: {str(e)}"}


def parse_mrz(mrz_line: str) -> dict:
    """Parse MRZ line and extract passport information"""
    try:
        mrz = mrz_line.strip()
 
        pattern = re.compile(r'([A-Z0-9<]{9})(\d)([A-Z]{3})(\d{6})(\d)([MF<])(\d{6})(\d)')
        m = pattern.search(mrz)
        if not m:
            return {"error": "MRZ pattern not found", "raw": mrz}
 
        passport_number_raw = m.group(1)
        passport_number = passport_number_raw.replace('<', '')
        nationality = m.group(3)
        birth_raw = m.group(4)
        gender = m.group(6) if m.group(6) != '<' else ''
        expiry_raw = m.group(7)
 
        names_start = 5
        names_end = m.start()
        names_section = mrz[names_start:names_end]
        parts = names_section.split('<<', 1)
        surname = parts[0].replace('<', '') if parts else ''
        given_raw = parts[1] if len(parts) > 1 else ''
        given_parts = [p for p in given_raw.split('<') if p]
        given_names = ' '.join(given_parts)
 
        birth_date = format_date(birth_raw)
        expiry_date = format_date(expiry_raw)
 
        try:
            expiry_dt = datetime.datetime.strptime(expiry_date, "%Y-%m-%d")
            issued_year = expiry_dt.year - 7
            issued_day = expiry_dt.day + 1
            try:
                issued_dt = expiry_dt.replace(year=issued_year, day=issued_day)
            except ValueError:
                next_month = expiry_dt.month + 1 if expiry_dt.month < 12 else 1
                next_year = issued_year if expiry_dt.month < 12 else issued_year + 1
                issued_dt = expiry_dt.replace(year=issued_year, month=next_month, day=1)
            issued_date = issued_dt.strftime("%Y-%m-%d")
        except Exception as e:
            logger.error(f"Error computing issued date: {e}")
            issued_date = "Unknown"
 
        result = {
            "passport_type": mrz[0] if len(mrz) > 0 else '',
            "country_code": mrz[2:5],
            "full_name": f"{given_names} {surname}".strip(),
            "surname": surname,
            "given_names": given_names,
            "passport_number": passport_number,
            "nationality": nationality,
            "birth_date": birth_date,
            "gender": gender,
            "expiry_date": expiry_date,
            "issued_date": issued_date,
        }
 
        return result
 
    except Exception as e:
        return {
            "error": str(e),
            "raw": mrz_line
        }
 
 
def process_passport_file_json(file_path: str) -> dict:
    """
    Process a single passport file (PDF or image) and extract MRZ data.
    Returns JSON directly with the required format.
   
    Args:
        file_path: Path to the passport file
       
    Returns:
        JSON dictionary with passport information:
        {
            "NameInPassport": str,
            "PassportNum": str,
            "ExpiryDate": str,
            "error": str (optional, if processing failed)
        }
    """
    try:
        passport = None
        extension = file_path.split('.')[-1].lower()
       
        if extension == 'pdf':
            import fitz
           
            doc = fitz.open(file_path)
           
            if len(doc) > 0:
                page = doc[0]
                pix = page.get_pixmap(dpi=600)
               
                img_data = pix.samples
                passport = np.frombuffer(img_data, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
               
                if pix.n == 4:
                    passport = cv2.cvtColor(passport, cv2.COLOR_RGBA2BGR)
                elif pix.n == 1:
                    passport = cv2.cvtColor(passport, cv2.COLOR_GRAY2BGR)
            else:
                return {"error": "PDF file has no pages"}
               
        elif extension in ['jpg', 'jpeg', 'png', 'bmp', 'tiff']:
            passport = cv2.imread(file_path)
            if passport is None:
                return {"error": f"Could not read image file: {file_path}"}
        else:
            return {"error": f"Unsupported file format: {extension}"}
 
        passport = get_lower_left(passport)
        passport = detect_barcode(passport)
       
        scale_factor = 4
        passport = cv2.resize(passport, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
       
        barcodes = zxingcpp.read_barcodes(passport)
       
        if not barcodes:
            logger.warning("No MRZ barcode detected, attempting OCR fallback...")
            
            # Convert numpy array to bytes for OCR
            try:
                # Convert BGR to RGB for PIL
                passport_rgb = cv2.cvtColor(passport, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(passport_rgb)
                
                # Convert to bytes
                img_byte_arr = io.BytesIO()
                pil_image.save(img_byte_arr, format='PNG')
                image_bytes = img_byte_arr.getvalue()
                
                # Use OCR to extract text
                ocr_text = ocr_passport(image_bytes)
                
                if not ocr_text or len(ocr_text) < 20:
                    return {"error": "No MRZ barcode detected and OCR extraction failed"}
                
                # Try to find MRZ lines in OCR text
                lines = ocr_text.split('\n')
                mrz_candidates = []
                
                # Strategy 1: Find complete MRZ lines (40+ chars with <)
                for line in lines:
                    line = line.strip().upper()
                    # MRZ lines are typically 44 chars and contain P< or V<
                    if len(line) >= 30 and ('P<' in line or '<<' in line or line.count('<') > 3):
                        # Clean the line
                        cleaned = re.sub(r'[^A-Z0-9<]', '', line)
                        if len(cleaned) >= 30:
                            mrz_candidates.append(cleaned)
                
                # Strategy 2: Reconstruct fragmented MRZ (if no complete lines found)
                if not mrz_candidates:
                    logger.info("No complete MRZ found, attempting to reconstruct from fragments...")
                    
                    # Find fragments that look like MRZ parts
                    fragments = []
                    for line in lines:
                        line_clean = line.strip().upper()
                        line_clean = re.sub(r'[^A-Z0-9<]', '', line_clean)
                        
                        # MRZ fragments: start with P<, contain passport numbers, or have many <
                        if (line_clean.startswith('P<') or 
                            re.search(r'[A-Z]\d{7,9}', line_clean) or  # Passport number pattern
                            line_clean.count('<') >= 2):
                            fragments.append(line_clean)
                    
                    # Try to reconstruct MRZ lines by separating line 1 and line 2
                    if len(fragments) >= 1:
                        # Strategy: Line 1 starts with P<, Line 2 starts with passport number
                        line1 = None
                        line2 = None
                        
                        for frag in fragments:
                            # Line 1: starts with P< (names section)
                            if frag.startswith('P<') and not line1:
                                line1 = frag
                            # Line 2: starts with passport number pattern (letter + digits)
                            elif re.match(r'^[A-Z]\d{7,9}', frag) and not line2:
                                line2 = frag
                        
                        # Add the separated lines as candidates
                        if line1 and len(line1) >= 30:
                            mrz_candidates.append(line1)
                            logger.info(f"Found MRZ Line 1: {line1}")
                        
                        if line2 and len(line2) >= 30:
                            mrz_candidates.append(line2)
                            logger.info(f"Found MRZ Line 2: {line2}")
                        
                        # Try combining line 1 and line 2 as separate MRZ lines
                        # The parse_mrz function needs line 2 to parse successfully
                        if line2 and len(line2) >= 30:
                            # Pad line 1 if available to create proper MRZ context
                            if line1:
                                # Try parsing line 2 with line 1 context for names
                                combined = line1 + line2
                                mrz_candidates.insert(0, combined)  # Prioritize combined
                                logger.info(f"Combined MRZ attempt: {combined[:88]}")
                
                if not mrz_candidates:
                    return {"error": "No valid MRZ found in OCR text", "ocr_text": ocr_text[:200]}
                
                # Try to parse MRZ candidates
                for mrz_line in mrz_candidates:
                    parsed = parse_mrz(mrz_line)
                    if "error" not in parsed:
                        parsed["extraction_method"] = "OCR_MRZ"
                        
                        # Validate with Pydantic
                        try:
                            validated = PassportData(**parsed)
                            logger.info("✓ Pydantic validation successful for OCR extraction")
                            logger.info(f"✓ Extracted: {validated.full_name}, Passport: {validated.passport_number}")
                            return validated.model_dump(by_alias=False, exclude_none=True)
                        except Exception as validation_error:
                            logger.warning(f"Pydantic validation warning: {validation_error}")
                            # Return raw data if validation fails
                            return parsed
                
                # If MRZ parsing failed, try LLM extraction as last resort
                logger.info("MRZ parsing failed, attempting LLM extraction from OCR text...")
                llm_extracted = extract_passport_with_llm(ocr_text)
                if llm_extracted and "error" not in llm_extracted:
                    logger.info("✓ LLM extraction successful")
                    return llm_extracted
                
                return {"error": "Could not parse MRZ from OCR text", "mrz_candidates": mrz_candidates[:3], "ocr_text": ocr_text[:200]}
                
            except Exception as ocr_error:
                logger.error(f"OCR fallback failed: {ocr_error}")
                traceback.print_exc()
                return {"error": f"No MRZ detected and OCR failed: {str(ocr_error)}"}
       
        for barcode in barcodes:
            try:
                text = barcode.text
                print('hola text', text)
                parsed = parse_mrz(text)
                print('hola parsed', parsed)
                if "error" not in parsed:
                    # Validate with Pydantic
                    try:
                        parsed['extraction_method'] = 'MRZ_barcode'
                        validated = PassportData(**parsed)
                        logger.info("✓ Pydantic validation successful for MRZ barcode extraction")
                        return validated.model_dump(by_alias=False, exclude_none=True)
                    except Exception as validation_error:
                        logger.warning(f"Pydantic validation warning: {validation_error}")
                        # Return raw data if validation fails
                        return parsed
            except Exception as e:
                logger.error(f"Error parsing barcode: {e}")
                continue
        return {"error": "Could not parse MRZ data from detected barcodes"}
       
    except Exception as e:
        logger.error(f"Error processing passport file {file_path}: {e}")
        traceback.print_exc()
        return {"error": f"Processing error: {str(e)}"}
