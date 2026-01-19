import os
import traceback
import zxingcpp
import re
import datetime
import cv2
import numpy as np
import logging
from Utils.ocr_engine import ocr_passport
import io
from PIL import Image
from Models.PassportModels import PassportData

logger = logging.getLogger(__name__)


def get_lower_left(image):
    """Extract the lower left quadrant where MRZ is typically located"""
    height, width = image.shape[:2]
    return image[height // 2:, :width // 2]


def detect_barcode(image):
    """
    Detect and crop barcode/MRZ region from passport image.
    Enhanced version with improved MRZ detection for horizontal text patterns.
    """
    # Keep the original image intact
    original = image.copy()

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # For MRZ detection: use gradient magnitude (not difference) to capture horizontal text patterns
    gradX = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
    gradY = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=0, dy=1, ksize=-1)
    # Use gradient magnitude instead of subtraction to preserve horizontal structures
    gradient = cv2.magnitude(gradX, gradY)
    gradient = cv2.convertScaleAbs(gradient)

    # Blur and threshold - lower threshold to capture more detail
    blurred = cv2.blur(gradient, (5, 5))  # Smaller blur to preserve detail
    _, thresh = cv2.threshold(blurred, 50, 255, cv2.THRESH_BINARY)  # Lower threshold

    # Morphological operations - larger horizontal kernel for MRZ text lines
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 5))  # Wider, shorter for text lines
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    # Remove small blobs - reduced iterations to preserve thin structures
    closed = cv2.erode(closed, None, iterations=2)  # Reduced from 4
    closed = cv2.dilate(closed, None, iterations=2)  # Reduced from 4

    # Find contours
    cnts, _ = cv2.findContours(closed.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        c = sorted(cnts, key=cv2.contourArea, reverse=True)[0]
        x, y, w, h = cv2.boundingRect(c)

        # Tight horizontal margins, generous vertical margins for MRZ lines
        margin_x = int(w * 0.01)  # Minimal horizontal margin (1%)
        margin_y = int(h * 0.8)   # Generous vertical margin to capture both MRZ lines
        x_exp = max(x - margin_x, 0)
        y_exp = max(y - margin_y, 0)
        w_exp = min(w + 2 * margin_x, original.shape[1] - x_exp)
        h_exp = min(h + 2 * margin_y, original.shape[0] - y_exp)

        # CRITICAL: Crop from the ORIGINAL image, not the processed one!
        cropped = original[y_exp:y_exp + h_exp, x_exp:x_exp + w_exp]

        return cropped

    # If no barcode detected, return the original image
    logger.warning("No barcode region detected, returning original image")
    return original


def format_date(s: str) -> str:
    """Format MRZ date string (YYMMDD) to ISO format (YYYY-MM-DD)"""
    yy = int(s[0:2])
    mm = int(s[2:4])
    dd = int(s[4:6])
    
    # Use sliding window: 00-50 -> 2000-2050, 51-99 -> 1951-1999
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
    """Parse MRZ line and extract passport information with improved fragment handling"""
    try:
        # Clean MRZ text - remove any non-MRZ characters
        mrz_clean = re.sub(r'[^A-Z0-9<]', '', mrz_line.upper())
        
        logger.info(f"Attempting to parse MRZ (length={len(mrz_clean)}): {mrz_clean[:88] if len(mrz_clean) > 88 else mrz_clean}")
        
        # Try to identify the two MRZ lines
        # Line 1: P<COUNTRYNAME<<GIVENNAMES<<<<<<<<<<<<<<<
        # Line 2: PASSPORTNUMCOUNTRYBIRTHGENDEREXPIRYCHECKSUM
        
        line1 = None
        line2 = None
        
        # Strategy 1: Split if we have exactly 88 characters (2 lines of 44)
        if len(mrz_clean) == 88:
            line1 = mrz_clean[:44]
            line2 = mrz_clean[44:88]
        # Strategy 2: Find line1 (starts with P<) and line2 (starts with passport num)
        elif mrz_clean.startswith('P<'):
            # Line 1 could be variable length, find where line 2 starts
            # Line 2 starts with passport number: letter followed by 7-9 digits
            match = re.search(r'([A-Z]\d{7,9}[A-Z]{3}\d{7}[MF]\d{7})', mrz_clean)
            if match:
                line2_start = match.start()
                line1 = mrz_clean[:line2_start]
                line2 = mrz_clean[line2_start:]
        # Strategy 3: If we have a passport number pattern, that's line 2
        elif re.match(r'^[A-Z]\d{7,9}', mrz_clean):
            line2 = mrz_clean
        
        # Pad lines to 44 characters if needed
        if line1 and len(line1) < 44:
            line1 = line1 + '<' * (44 - len(line1))
        if line2 and len(line2) < 44:
            line2 = line2 + '<' * (44 - len(line2))
        
        # Extract data
        result = {}
        
        # From Line 1 (if available): P<COUNTRYNAME<<GIVENNAMES<<<<<<
        if line1:
            result['passport_type'] = line1[0]  # Should be 'P'
            result['country_code'] = line1[2:5].replace('<', '')  # 3-letter code
            
            # Name extraction: everything after country code
            name_section = line1[5:].replace('<', ' ').strip()
            name_parts = [p for p in name_section.split(' ') if p]
            
            if name_parts:
                result['surname'] = name_parts[0]
                result['given_names'] = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                result['full_name'] = f"{' '.join(name_parts[1:])} {name_parts[0]}" if len(name_parts) > 1 else name_parts[0]
        
        # From Line 2 (required): PASSPORTNUMCOUNTRYBIRTHGENDEREXPIRY
        if line2:
            # Passport number: positions 0-8 (letter + 8 digits, but can vary)
            passport_match = re.match(r'^([A-Z]\d{7,9})', line2)
            if passport_match:
                result['passport_number'] = passport_match.group(1).rstrip('<')
                pos = len(passport_match.group(1))
            else:
                # Try to extract first alphanumeric sequence
                passport_match = re.match(r'^([A-Z0-9]+)', line2)
                if passport_match:
                    result['passport_number'] = passport_match.group(1).rstrip('<')
                    pos = len(passport_match.group(1))
                else:
                    pos = 0
            
            # Skip check digit
            pos += 1
            
            # Nationality: 3 letters
            if pos + 3 <= len(line2):
                result['nationality'] = line2[pos:pos+3].replace('<', '')
                pos += 3
            
            # Birth date: 6 digits (YYMMDD)
            if pos + 6 <= len(line2):
                birth_str = line2[pos:pos+6]
                if birth_str.isdigit():
                    result['birth_date'] = format_date(birth_str)
                pos += 6
            
            # Skip check digit
            pos += 1
            
            # Gender: 1 character
            if pos < len(line2):
                result['gender'] = line2[pos]
                pos += 1
            
            # Expiry date: 6 digits (YYMMDD)
            if pos + 6 <= len(line2):
                expiry_str = line2[pos:pos+6]
                if expiry_str.isdigit():
                    result['expiry_date'] = format_date(expiry_str)
                    # Calculate issue date (typically 10 years before expiry for most passports)
                    try:
                        expiry = datetime.datetime.strptime(result['expiry_date'], '%Y-%m-%d')
                        issue = expiry - datetime.timedelta(days=3652)  # ~10 years
                        result['issued_date'] = issue.strftime('%Y-%m-%d')
                    except:
                        pass
                pos += 6
        
        # Validation
        required_fields = ['passport_number']
        if not all(field in result and result[field] for field in required_fields):
            logger.warning(f"Missing required fields in MRZ parse: {result}")
            return {"error": "Incomplete MRZ data", "partial": result}
        
        logger.info(f"Successfully parsed MRZ: {result.get('full_name', 'N/A')} - {result.get('passport_number', 'N/A')}")
        return result
        
    except Exception as e:
        logger.error(f"Error parsing MRZ: {e}")
        return {"error": str(e)}


def reconstruct_mrz_from_fragments(ocr_text: str) -> list:
    """
    Intelligently reconstruct MRZ lines from fragmented OCR text.
    Returns list of candidate MRZ strings to try parsing.
    """
    candidates = []
    lines = ocr_text.split('\n')
    
    # Clean and filter lines
    cleaned_lines = []
    for line in lines:
        line_clean = line.strip().upper()
        # Remove non-MRZ characters
        line_clean = re.sub(r'[^A-Z0-9<]', '', line_clean)
        if line_clean and len(line_clean) >= 10:  # Minimum fragment length
            cleaned_lines.append(line_clean)
    
    logger.info(f"Found {len(cleaned_lines)} potential MRZ fragments")
    for i, line in enumerate(cleaned_lines):
        logger.info(f"  Fragment {i+1}: {line}")
    
    # Strategy 1: Look for complete or near-complete MRZ lines
    for line in cleaned_lines:
        if len(line) >= 30 and ('P<' in line or '<<' in line or line.count('<') > 3):
            candidates.append(line)
            logger.info(f"✓ Found candidate MRZ line: {line[:50]}...")
    
    # Strategy 2: Identify and reconstruct Line 1 (names) and Line 2 (numbers)
    line1_fragments = []
    line2_fragments = []
    
    for line in cleaned_lines:
        # Line 1: starts with P< or contains name patterns
        if line.startswith('P<') or (line.count('<') > 2 and not re.search(r'\d{6}', line)):
            line1_fragments.append(line)
        # Line 2: contains passport number pattern or dates
        elif re.search(r'[A-Z]\d{7,9}', line) or re.search(r'\d{6}', line):
            line2_fragments.append(line)
    
    logger.info(f"Identified {len(line1_fragments)} Line1 fragments, {len(line2_fragments)} Line2 fragments")
    
    # Try to combine fragments
    if line1_fragments and line2_fragments:
        # Take the longest/most complete fragments
        line1 = max(line1_fragments, key=len)
        line2 = max(line2_fragments, key=len)
        
        # Combine them
        combined = line1 + line2
        candidates.insert(0, combined)  # Prioritize combined version
        logger.info(f"✓ Reconstructed combined MRZ: {combined[:88] if len(combined) > 88 else combined}")
        
        # Also try them separately
        if len(line2) >= 30:
            candidates.append(line2)  # Line 2 alone can sometimes work
    
    elif line2_fragments:
        # We have line 2 but not line 1 - still worth trying
        line2 = max(line2_fragments, key=len)
        candidates.append(line2)
        logger.info(f"✓ Found Line2 only: {line2}")
    
    # Strategy 3: Try concatenating adjacent lines that look MRZ-like
    for i in range(len(cleaned_lines) - 1):
        combined = cleaned_lines[i] + cleaned_lines[i+1]
        if len(combined) >= 44 and combined.count('<') > 5:
            candidates.append(combined)
            logger.info(f"✓ Concatenated adjacent lines: {combined[:50]}...")
    
    return candidates


def process_passport_file_json(file_path: str) -> dict:
    """
    Process passport file and extract information using barcode detection and MRZ parsing.
    Falls back to OCR if barcode detection fails.
    
    Args:
        file_path: Path to passport image file
        
    Returns:
        Dictionary containing extracted passport information or error
    """
    try:
        # Load image
        if file_path.lower().endswith('.pdf'):
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_data = pix.tobytes("png")
            nparr = np.frombuffer(img_data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        else:
            image = cv2.imread(file_path)
        
        if image is None:
            return {"error": "Could not load image"}
        
        # Try barcode detection first
        cropped = detect_barcode(image)
        
        # Convert to PIL Image for zxing
        cropped_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(cropped_rgb)
        
        # Try to read barcodes/MRZ from the cropped region
        barcodes = zxingcpp.read_barcodes(pil_image)
        
        # If no barcodes detected, fall back to OCR
        if not barcodes or len(barcodes) == 0:
            logger.warning("No MRZ barcode detected, attempting OCR fallback...")
            
            try:
                # Read the file as bytes for OCR
                with open(file_path, 'rb') as f:
                    image_bytes = f.read()
                
                # Perform OCR
                ocr_text = ocr_passport(image_bytes)
                logger.info(f"OCR extracted text (length={len(ocr_text)})")
                logger.info(f"OCR text preview: {ocr_text[:200]}")
                
                # Try to find and reconstruct MRZ from OCR text
                mrz_candidates = reconstruct_mrz_from_fragments(ocr_text)
                
                if not mrz_candidates:
                    logger.warning("No MRZ candidates found, trying LLM extraction...")
                    llm_result = extract_passport_with_llm(ocr_text)
                    if llm_result and "error" not in llm_result:
                        return llm_result
                    return {"error": "No valid MRZ found in OCR text", "ocr_text": ocr_text[:200]}
                
                # Try to parse each MRZ candidate
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
                
                return {
                    "error": "Could not parse MRZ from OCR text", 
                    "mrz_candidates": mrz_candidates[:3],
                    "ocr_text": ocr_text[:200]
                }
                
            except Exception as ocr_error:
                logger.error(f"OCR fallback failed: {ocr_error}")
                traceback.print_exc()
                return {"error": f"No MRZ detected and OCR failed: {str(ocr_error)}"}
        
        # Try to parse the first valid barcode
        for barcode in barcodes:
            try:
                text = barcode.text
                logger.info(f"Barcode detected, parsing MRZ...")
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


def generate_passport_html(passports_data: list) -> str:
    """
    Generate HTML table from list of passport data
    
    Args:
        passports_data: List of dictionaries containing passport information
        
    Returns:
        HTML string with formatted passport information
    """
    if not passports_data:
        return """
        <div class="p-6 bg-yellow-50 border border-yellow-200 rounded-lg">
            <p class="text-yellow-700 text-center">No passports uploaded</p>
        </div>
        """
    
    html = """
    <div class="p-6 bg-white border rounded-lg shadow-sm">
        <h3 class="text-xl font-semibold text-gray-800 mb-4">Extracted Passport Information</h3>
    """
    
    for idx, passport in enumerate(passports_data, 1):
        if "error" in passport:
            html += f"""
            <div class="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
                <h4 class="text-lg font-semibold text-red-700 mb-2">Passport #{idx} - Error</h4>
                <p class="text-red-600">{passport.get('error', 'Unknown error')}</p>
                {f'<p class="text-sm text-gray-600 mt-1">File: {passport.get("filename", "Unknown")}</p>' if passport.get("filename") else ''}
                {f'<p class="text-xs text-gray-500 mt-1 font-mono">Raw: {passport.get("raw", "")}</p>' if passport.get("raw") else ''}
            </div>
            """
        else:
            html += f"""
            <div class="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <h4 class="text-lg font-semibold text-blue-700 mb-3">Passport #{idx}</h4>
                {f'<p class="text-sm text-gray-600 mb-3">File: {passport.get("filename", "Unknown")}</p>' if passport.get("filename") else ''}
                <table class="min-w-full bg-white border border-gray-300 rounded-lg overflow-hidden">
                    <tbody>
                        <tr class="border-b">
                            <td class="px-4 py-2 font-semibold text-gray-700 bg-gray-50">Full Name</td>
                            <td class="px-4 py-2 text-gray-900">{passport.get('full_name', 'N/A')}</td>
                        </tr>
                        <tr class="border-b">
                            <td class="px-4 py-2 font-semibold text-gray-700 bg-gray-50">Surname</td>
                            <td class="px-4 py-2 text-gray-900">{passport.get('surname', 'N/A')}</td>
                        </tr>
                        <tr class="border-b">
                            <td class="px-4 py-2 font-semibold text-gray-700 bg-gray-50">Given Names</td>
                            <td class="px-4 py-2 text-gray-900">{passport.get('given_names', 'N/A')}</td>
                        </tr>
                        <tr class="border-b">
                            <td class="px-4 py-2 font-semibold text-gray-700 bg-gray-50">Passport Number</td>
                            <td class="px-4 py-2 text-gray-900 font-mono">{passport.get('passport_number', 'N/A')}</td>
                        </tr>
                        <tr class="border-b">
                            <td class="px-4 py-2 font-semibold text-gray-700 bg-gray-50">Nationality</td>
                            <td class="px-4 py-2 text-gray-900">{passport.get('nationality', 'N/A')}</td>
                        </tr>
                        <tr class="border-b">
                            <td class="px-4 py-2 font-semibold text-gray-700 bg-gray-50">Country Code</td>
                            <td class="px-4 py-2 text-gray-900">{passport.get('country_code', 'N/A')}</td>
                        </tr>
                        <tr class="border-b">
                            <td class="px-4 py-2 font-semibold text-gray-700 bg-gray-50">Date of Birth</td>
                            <td class="px-4 py-2 text-gray-900">{passport.get('birth_date', 'N/A')}</td>
                        </tr>
                        <tr class="border-b">
                            <td class="px-4 py-2 font-semibold text-gray-700 bg-gray-50">Gender</td>
                            <td class="px-4 py-2 text-gray-900">{passport.get('gender', 'N/A')}</td>
                        </tr>
                        <tr class="border-b">
                            <td class="px-4 py-2 font-semibold text-gray-700 bg-gray-50">Issue Date</td>
                            <td class="px-4 py-2 text-gray-900">{passport.get('issued_date', 'N/A')}</td>
                        </tr>
                        <tr class="border-b">
                            <td class="px-4 py-2 font-semibold text-gray-700 bg-gray-50">Expiry Date</td>
                            <td class="px-4 py-2 text-gray-900">{passport.get('expiry_date', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td class="px-4 py-2 font-semibold text-gray-700 bg-gray-50">Passport Type</td>
                            <td class="px-4 py-2 text-gray-900">{passport.get('passport_type', 'N/A')}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            """
    
    html += "</div>"
    return html