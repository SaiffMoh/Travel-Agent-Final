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
    try:
        yy = int(s[0:2])
        mm = int(s[2:4])
        dd = int(s[4:6])
       
        if yy <= 50:
            year = 2000 + yy
        else:
            year = 1900 + yy
       
        return f"{year:04d}-{mm:02d}-{dd:02d}"
    except:
        return ""
 
 
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
        logger.error(traceback.format_exc())
        return {"error": f"LLM extraction failed: {str(e)}"}


def parse_mrz_flexible(mrz_line: str) -> dict:
    """
    Flexible MRZ parser that handles both complete and partial MRZ data.
    Works with fragments and reconstructed MRZ lines.
    """
    try:
        mrz_clean = re.sub(r'[^A-Z0-9<]', '', mrz_line.upper().strip())
        logger.info(f"Parsing MRZ (length={len(mrz_clean)}): {mrz_clean[:100]}")
        
        result = {}
        
        # Identify Line 1 (names) and Line 2 (data)
        line1 = None
        line2 = None
        
        # Strategy 1: If we have ~88 chars, split in half
        if len(mrz_clean) >= 80 and len(mrz_clean) <= 100:
            line1 = mrz_clean[:44]
            line2 = mrz_clean[44:88] if len(mrz_clean) >= 88 else mrz_clean[44:]
        # Strategy 2: Find where line2 starts (passport number pattern)
        elif mrz_clean.startswith('P<'):
            # Look for passport number pattern in the string
            match = re.search(r'([A-Z]\d{7,9}[A-Z0-9<]{3}\d)', mrz_clean)
            if match:
                split_pos = match.start()
                line1 = mrz_clean[:split_pos]
                line2 = mrz_clean[split_pos:]
        # Strategy 3: Just have line2 (passport number)
        elif re.match(r'^[A-Z]\d{7,9}', mrz_clean):
            line2 = mrz_clean
        
        # Extract from Line 1 (names)
        if line1:
            result['passport_type'] = line1[0] if len(line1) > 0 else 'P'
            result['country_code'] = line1[2:5].replace('<', '') if len(line1) >= 5 else ''
            
            # Extract names
            name_section = line1[5:].replace('<', ' ').strip() if len(line1) > 5 else ''
            name_parts = [p for p in name_section.split() if p]
            
            if name_parts:
                result['surname'] = name_parts[0]
                result['given_names'] = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                result['full_name'] = f"{' '.join(name_parts[1:])} {name_parts[0]}".strip() if len(name_parts) > 1 else name_parts[0]
        
        # Extract from Line 2 (passport number, dates, etc)
        if line2:
            pos = 0
            
            # Passport number (variable length, letter + 7-9 digits)
            passport_match = re.match(r'^([A-Z]\d{7,9})', line2)
            if passport_match:
                result['passport_number'] = passport_match.group(1)
                pos = len(passport_match.group(1))
                
                # Skip check digit (usually 1 digit, but could be '<')
                if pos < len(line2) and (line2[pos].isdigit() or line2[pos] == '<'):
                    pos += 1
                
                # Nationality (3 letters) - handle truncation
                if pos + 3 <= len(line2):
                    nationality_raw = line2[pos:pos+3]
                    # Clean nationality and validate it's 3 letters
                    nationality = nationality_raw.replace('<', '')
                    
                    # If nationality looks wrong (e.g., 'GY9'), try to find 3 consecutive letters
                    if not nationality.isalpha() or len(nationality) < 2:
                        # Look for pattern like 'EGY' in the surrounding text
                        nat_match = re.search(r'([A-Z]{3})', line2[max(0, pos-5):pos+10])
                        if nat_match:
                            nationality = nat_match.group(1)
                            logger.info(f"Corrected nationality from '{nationality_raw}' to '{nationality}'")
                    
                    result['nationality'] = nationality
                    result['country_code'] = result.get('country_code') or nationality
                    pos += 3
                
                # Birth date (6 digits)
                # Look ahead to find 6 consecutive digits (could be offset if parsing went wrong)
                birth_match = re.search(r'(\d{6})', line2[pos:])
                if birth_match:
                    birth_str = birth_match.group(1)
                    result['birth_date'] = format_date(birth_str)
                    pos = pos + birth_match.end()
                
                # Skip check digit
                if pos < len(line2) and (line2[pos].isdigit() or line2[pos] == '<'):
                    pos += 1
                
                # Gender (1 char)
                if pos < len(line2):
                    gender = line2[pos]
                    result['gender'] = gender if gender in ['M', 'F'] else ''
                    pos += 1
                
                # Expiry date (6 digits) - search for next 6-digit sequence
                expiry_match = re.search(r'(\d{6})', line2[pos:])
                if expiry_match:
                    expiry_str = expiry_match.group(1)
                    result['expiry_date'] = format_date(expiry_str)
                    
                    # Calculate issue date (typically 10 years before expiry)
                    try:
                        expiry_dt = datetime.datetime.strptime(result['expiry_date'], "%Y-%m-%d")
                        issued_year = expiry_dt.year - 10
                        issued_day = expiry_dt.day + 1
                        try:
                            issued_dt = expiry_dt.replace(year=issued_year, day=issued_day)
                        except ValueError:
                            issued_dt = expiry_dt.replace(year=issued_year, day=1)
                        result['issued_date'] = issued_dt.strftime("%Y-%m-%d")
                    except:
                        pass
        
        # Validation - must have at least passport number
        if not result.get('passport_number'):
            return {"error": "Could not extract passport number", "raw": mrz_clean[:100]}
        
        logger.info(f"✓ Successfully parsed: {result.get('full_name', 'N/A')} - {result.get('passport_number')}")
        return result
        
    except Exception as e:
        logger.error(f"Error in parse_mrz_flexible: {e}")
        return {"error": str(e), "raw": mrz_line[:100]}


def parse_mrz(mrz_line: str) -> dict:
    """Parse MRZ line and extract passport information - original strict version"""
    try:
        mrz = mrz_line.strip()
 
        pattern = re.compile(r'([A-Z0-9<]{9})(\d)([A-Z]{3})(\d{6})(\d)([MF<])(\d{6})(\d)')
        m = pattern.search(mrz)
        if not m:
            # Fall back to flexible parser
            return parse_mrz_flexible(mrz_line)
 
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
        # Fall back to flexible parser
        return parse_mrz_flexible(mrz_line)


def reconstruct_mrz_smart(lines: list) -> list:
    """
    Smart MRZ reconstruction from OCR fragments.
    Returns list of candidate MRZ strings to try.
    """
    candidates = []
    
    # Clean all lines
    cleaned_lines = []
    for line in lines:
        line_clean = line.strip().upper()
        line_clean = re.sub(r'[^A-Z0-9<]', '', line_clean)
        if line_clean and len(line_clean) >= 10:
            cleaned_lines.append(line_clean)
    
    logger.info(f"Processing {len(cleaned_lines)} cleaned lines for MRZ reconstruction")
    for i, line in enumerate(cleaned_lines):
        logger.info(f"  Line {i+1}: {line}")
    
    # Strategy 1: Find complete MRZ lines
    for line in cleaned_lines:
        if len(line) >= 35 and (line.startswith('P<') or line.count('<') > 3):
            candidates.append(line)
            logger.info(f"✓ Complete MRZ candidate: {line[:50]}...")
    
    # Strategy 2: Identify Line 1 (names) and Line 2 (data) fragments
    line1_candidates = []
    line2_candidates = []
    
    for line in cleaned_lines:
        # Line 1: starts with P< or has << separator
        if line.startswith('P<') or '<<' in line:
            line1_candidates.append(line)
            logger.info(f"  → Line1 candidate: {line}")
        # Line 2: starts with passport number (letter + digits)
        elif re.match(r'^[A-Z]\d{7,9}', line):
            line2_candidates.append(line)
            logger.info(f"  → Line2 candidate: {line}")
    
    # Strategy 3: Combine the best Line1 + Line2
    if line1_candidates and line2_candidates:
        # Score each Line1 candidate based on quality indicators
        def score_line1(line):
            score = len(line)  # Base score is length
            
            # Bonus for having << separator (indicates proper name structure)
            if '<<' in line:
                score += 20
            
            # Bonus for having more < characters (proper MRZ structure)
            score += line.count('<') * 2
            
            # Penalty for having digits (shouldn't be in name section)
            score -= sum(1 for c in line if c.isdigit()) * 5
            
            return score
        
        # Select best Line1 based on score
        line1 = max(line1_candidates, key=score_line1)
        line2 = max(line2_candidates, key=len)
        
        logger.info(f"Best Line1 (len={len(line1)}): {line1}")
        logger.info(f"Best Line2 (len={len(line2)}): {line2}")
        
        # Pad to 44 characters if needed
        if len(line1) < 44:
            line1 = line1 + '<' * (44 - len(line1))
        if len(line2) < 44:
            line2 = line2 + '<' * (44 - len(line2))
        
        combined = line1 + line2
        candidates.insert(0, combined)  # Prioritize combined
        logger.info(f"✓ Reconstructed MRZ: {combined[:88]}")
        
        # ALSO try other line1 candidates if we have multiple
        # This helps when OCR produces multiple attempts at the name line
        if len(line1_candidates) > 1:
            # Sort by score to try better quality versions first
            sorted_line1 = sorted(line1_candidates, key=score_line1, reverse=True)
            for alt_line1 in sorted_line1[1:3]:  # Try up to 2 alternatives
                if alt_line1 != line1:  # Don't duplicate
                    alt_padded = alt_line1 + '<' * (44 - len(alt_line1)) if len(alt_line1) < 44 else alt_line1
                    alt_combined = alt_padded + line2
                    candidates.insert(1, alt_combined)  # Insert after primary candidate
                    logger.info(f"✓ Alternative MRZ with Line1: {alt_line1[:30]}...")
    
    # Strategy 4: Even if we only have Line2, try it
    elif line2_candidates:
        line2 = max(line2_candidates, key=len)
        candidates.append(line2)
        logger.info(f"✓ Line2 only: {line2}")
    
    # Strategy 5: Try concatenating adjacent lines
    for i in range(len(cleaned_lines) - 1):
        if len(cleaned_lines[i]) >= 20 and len(cleaned_lines[i+1]) >= 20:
            combined = cleaned_lines[i] + cleaned_lines[i+1]
            if combined.count('<') >= 3:
                candidates.append(combined)
                logger.info(f"✓ Adjacent concat: {combined[:60]}...")
    
    return candidates
 
 
def process_passport_file_json(file_path: str) -> dict:
    """
    Process a single passport file (PDF or image) and extract MRZ data.
    Returns JSON directly with the required format.
   
    Args:
        file_path: Path to the passport file
       
    Returns:
        JSON dictionary with passport information
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
                logger.info(f"OCR extracted {len(ocr_text)} characters")
                
                if not ocr_text or len(ocr_text) < 20:
                    logger.warning("OCR extraction too short, trying LLM...")
                    return extract_passport_with_llm("")
                
                # Log OCR output for debugging
                logger.info(f"OCR text:\n{ocr_text[:300]}")
                
                # Try to reconstruct MRZ from OCR text
                lines = ocr_text.split('\n')
                mrz_candidates = reconstruct_mrz_smart(lines)
                
                if not mrz_candidates:
                    logger.warning("No MRZ candidates found, falling back to LLM extraction...")
                    llm_result = extract_passport_with_llm(ocr_text)
                    return llm_result
                
                # Try to parse each MRZ candidate
                logger.info(f"Trying to parse {len(mrz_candidates)} MRZ candidates...")
                successful_parses = []
                
                for i, mrz_line in enumerate(mrz_candidates):
                    logger.info(f"Attempting candidate {i+1}/{len(mrz_candidates)}: {mrz_line[:60]}...")
                    parsed = parse_mrz(mrz_line)
                    
                    if "error" not in parsed and parsed.get('passport_number'):
                        # Validate with Pydantic
                        try:
                            validated = PassportData(**parsed)
                            parsed['extraction_method'] = 'OCR_MRZ'
                            successful_parses.append(parsed)
                            logger.info(f"✓ Candidate {i+1} parsed successfully: {parsed.get('full_name', 'N/A')} - {parsed.get('passport_number')}")
                        except Exception as validation_error:
                            logger.warning(f"Candidate {i+1} Pydantic validation failed: {validation_error}")
                            # Still keep it if it has passport number
                            if parsed.get('passport_number'):
                                parsed['extraction_method'] = 'OCR_MRZ'
                                successful_parses.append(parsed)
                                logger.info(f"✓ Candidate {i+1} kept (unvalidated): {parsed.get('full_name', 'N/A')}")
                    else:
                        logger.warning(f"Candidate {i+1} parse error: {parsed.get('error', 'Unknown')}")
                
                # If we have successful MRZ parses, select the best one
                mrz_result = None
                if successful_parses:
                    if len(successful_parses) == 1:
                        mrz_result = successful_parses[0]
                        logger.info("✓ Single successful MRZ parse")
                    else:
                        # Score each result based on completeness
                        def score_parse(p):
                            score = 0
                            # Prefer longer given names (more complete)
                            score += len(p.get('given_names', '')) * 2
                            # Prefer results with more fields filled
                            score += sum(1 for v in p.values() if v and v != '')
                            # Prefer results with proper nationality (3 letters, all alpha)
                            nat = p.get('nationality', '')
                            if len(nat) == 3 and nat.isalpha():
                                score += 10
                            return score
                        
                        mrz_result = max(successful_parses, key=score_parse)
                        logger.info(f"✓ Selected best of {len(successful_parses)} MRZ parses: {mrz_result.get('full_name', 'N/A')}")
                
                # ALWAYS try LLM extraction in parallel for comparison
                logger.info("Running LLM extraction in parallel for comparison...")
                llm_result = extract_passport_with_llm(ocr_text)
                
                # If we have both MRZ and LLM results, merge the best fields
                if mrz_result and llm_result and "error" not in llm_result:
                    logger.info("✓ Both MRZ and LLM extraction succeeded, merging best fields...")
                    
                    merged_result = {}
                    
                    # For each field, pick the better value
                    def is_better(new_val, old_val, field_name):
                        """Determine if new value is better than old value"""
                        if not new_val or new_val == '':
                            return False
                        if not old_val or old_val == '':
                            return True
                        
                        # For names, prefer longer/more complete
                        if field_name in ['full_name', 'given_names', 'surname']:
                            return len(str(new_val)) > len(str(old_val))
                        
                        # For nationality, prefer valid 3-letter codes
                        if field_name in ['nationality', 'country_code']:
                            if len(str(new_val)) == 3 and str(new_val).isalpha():
                                return True
                            return False
                        
                        # For structured fields (dates, passport number), prefer MRZ (more reliable)
                        if field_name in ['passport_number', 'birth_date', 'expiry_date', 'issued_date']:
                            # MRZ is more reliable for these, so only replace if LLM has it and MRZ doesn't
                            return False
                        
                        # For other fields, prefer non-empty
                        return True
                    
                    # Start with MRZ result as base (more reliable for structured data)
                    merged_result = mrz_result.copy()
                    
                    # Merge in LLM fields where they're better
                    for field in ['full_name', 'given_names', 'surname', 'nationality', 'country_code', 
                                  'gender', 'passport_type', 'birth_date', 'expiry_date', 'passport_number']:
                        llm_val = llm_result.get(field)
                        mrz_val = mrz_result.get(field)
                        
                        if is_better(llm_val, mrz_val, field):
                            merged_result[field] = llm_val
                            logger.info(f"  → Using LLM for {field}: '{llm_val}' (vs MRZ: '{mrz_val}')")
                        else:
                            logger.info(f"  → Using MRZ for {field}: '{mrz_val}'")
                    
                    merged_result['extraction_method'] = 'OCR_MRZ_LLM_hybrid'
                    
                    # Final Pydantic validation on merged result
                    try:
                        validated = PassportData(**merged_result)
                        logger.info("✓ Final Pydantic validation successful for hybrid extraction")
                        logger.info(f"✓ FINAL: {validated.full_name}, Passport: {validated.passport_number}")
                        return validated.model_dump(by_alias=False, exclude_none=True)
                    except Exception as validation_error:
                        logger.warning(f"Hybrid validation warning: {validation_error}")
                        return merged_result
                
                # If only MRZ succeeded
                elif mrz_result:
                    logger.info("✓ Using MRZ result (LLM extraction failed or not available)")
                    try:
                        validated = PassportData(**mrz_result)
                        logger.info("✓ Final Pydantic validation successful for OCR extraction")
                        logger.info(f"✓ Extracted: {validated.full_name}, Passport: {validated.passport_number}")
                        return validated.model_dump(by_alias=False, exclude_none=True)
                    except Exception as validation_error:
                        logger.warning(f"Final Pydantic validation warning: {validation_error}")
                        return mrz_result
                
                # If only LLM succeeded
                elif llm_result and "error" not in llm_result:
                    logger.info("✓ Using LLM result (MRZ parsing failed)")
                    return llm_result
                
                # Complete failure - no successful extraction
                logger.error("All extraction methods failed")
                return {
                    "error": "Could not extract passport data via MRZ or LLM", 
                    "ocr_text": ocr_text[:200],
                    "mrz_candidates_tried": len(mrz_candidates),
                    "mrz_successful_parses": len(successful_parses),
                    "llm_attempted": True
                }
                
            except Exception as ocr_error:
                logger.error(f"OCR fallback failed: {ocr_error}")
                logger.error(traceback.format_exc())
                return {"error": f"No MRZ detected and OCR failed: {str(ocr_error)}"}
       
        # Process barcodes
        for barcode in barcodes:
            try:
                text = barcode.text
                logger.info(f"Processing barcode: {text[:60]}...")
                parsed = parse_mrz(text)
                
                if "error" not in parsed:
                    # Validate with Pydantic
                    try:
                        parsed['extraction_method'] = 'MRZ_barcode'
                        validated = PassportData(**parsed)
                        logger.info("✓ Pydantic validation successful for MRZ barcode extraction")
                        return validated.model_dump(by_alias=False, exclude_none=True)
                    except Exception as validation_error:
                        logger.warning(f"Pydantic validation warning: {validation_error}")
                        # Return raw data if validation fails but has passport number
                        if parsed.get('passport_number'):
                            return parsed
            except Exception as e:
                logger.error(f"Error parsing barcode: {e}")
                continue
                
        return {"error": "Could not parse MRZ data from detected barcodes"}
       
    except Exception as e:
        logger.error(f"Error processing passport file {file_path}: {e}")
        traceback.print_exc()
        return {"error": f"Processing error: {str(e)}"}