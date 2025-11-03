"""
Utils/visa_decoder.py
Enhanced visa information extraction with improved text parsing and barcode detection.
Prioritizes direct text extraction from PDFs, uses OCR only as fallback.
"""
import os
import base64
import logging
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import fitz  # PyMuPDF
from PIL import Image, ImageEnhance
import io
import numpy as np
from paddleocr import PaddleOCR
import cv2
import zxingcpp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize PaddleOCR for English and Arabic (lazy loading)
import logging as paddle_logging
paddle_logging.getLogger('ppocr').setLevel(paddle_logging.ERROR)

ocr_engine_en = None
ocr_engine_ar = None


def get_ocr_engines():
    """Lazy load OCR engines only when needed."""
    global ocr_engine_en, ocr_engine_ar
    if ocr_engine_en is None:
        ocr_engine_en = PaddleOCR(use_angle_cls=True, lang='en')
    if ocr_engine_ar is None:
        ocr_engine_ar = PaddleOCR(use_angle_cls=True, lang='ar')
    return ocr_engine_en, ocr_engine_ar


class BarcodeParser:
    """Parse barcode data from visa documents."""
    
    @staticmethod
    def extract_barcode_from_pdf(pdf_path: str) -> Optional[str]:
        """
        Extract barcode directly from PDF page by rendering it.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Barcode text or None if not found
        """
        try:
            doc = fitz.open(pdf_path)
            page = doc[0]
            
            # Render page at very high DPI for better barcode detection
            pix = page.get_pixmap(dpi=400)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
            
            # Convert RGB to BGR for OpenCV
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # Try to read barcode
            barcode_text = BarcodeParser.detect_and_read_barcode(img_bgr)
            
            doc.close()
            return barcode_text
            
        except Exception as e:
            logger.error(f"Error extracting barcode from PDF: {e}")
            return None
    
    @staticmethod
    def detect_and_read_barcode(image: np.ndarray) -> Optional[str]:
        """
        Detect and read barcode from image with multiple preprocessing attempts.
        
        Args:
            image: numpy array of the image (BGR format)
            
        Returns:
            Barcode text or None if not found
        """
        try:
            # Try multiple preprocessing approaches
            attempts = [
                ('original', image),
                ('contrast', cv2.convertScaleAbs(image, alpha=1.8, beta=0)),
                ('gray_thresh', cv2.threshold(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 127, 255, cv2.THRESH_BINARY)[1]),
            ]
            
            all_barcodes = []
            
            for name, attempt_img in attempts:
                # Ensure it's in the right format
                if len(attempt_img.shape) == 2:  # Grayscale
                    attempt_img = cv2.cvtColor(attempt_img, cv2.COLOR_GRAY2BGR)
                
                # Upscale significantly for better detection
                scale_factor = 3
                upscaled = cv2.resize(attempt_img, None, fx=scale_factor, fy=scale_factor, 
                                    interpolation=cv2.INTER_CUBIC)
                
                # Try reading barcodes with different options
                barcodes = zxingcpp.read_barcodes(upscaled)
                
                if barcodes:
                    for barcode in barcodes:
                        if barcode.text and len(barcode.text) > 5:  # Filter out noise
                            all_barcodes.append((name, barcode.text))
                            logger.info(f"✓ Barcode found ({name}): {barcode.text[:80]}...")
            
            # Return the longest barcode found (likely to be most complete)
            if all_barcodes:
                best_barcode = max(all_barcodes, key=lambda x: len(x[1]))
                logger.info(f"Selected barcode: {best_barcode[1][:100]}...")
                return best_barcode[1]
            
            logger.info("✗ No barcode detected")
            return None
            
        except Exception as e:
            logger.error(f"Barcode detection error: {e}")
            return None
    
    @staticmethod
    def parse_visa_barcode(barcode_text: str) -> Dict[str, Any]:
        """
        Parse visa information from barcode text.
        
        Args:
            barcode_text: Raw barcode text
            
        Returns:
            Dictionary with parsed barcode data
        """
        data = {}
        
        try:
            logger.info(f"Parsing barcode text: {barcode_text[:200]}...")
            
            # Extract entry permit number (e.g., "206/2025/87553014")
            permit_match = re.search(r'(\d{3}/\d{4}/\d+)', barcode_text)
            if permit_match:
                data['barcode_entry_permit'] = permit_match.group(1)
                logger.info(f"  → Entry permit: {data['barcode_entry_permit']}")
            
            # Extract dates in various formats
            # Format: YYYY-MM-DD
            date_matches = re.findall(r'(\d{4}-\d{2}-\d{2})', barcode_text)
            if len(date_matches) >= 1:
                data['barcode_issue_date'] = date_matches[0]
                logger.info(f"  → Issue date: {data['barcode_issue_date']}")
            if len(date_matches) >= 2:
                data['barcode_expiry_date'] = date_matches[1]
                logger.info(f"  → Expiry date: {data['barcode_expiry_date']}")
            
            # Format: DD-MM-YYYY or DD/MM/YYYY
            if not date_matches:
                alt_dates = re.findall(r'(\d{2}[-/]\d{2}[-/]\d{4})', barcode_text)
                for i, date_str in enumerate(alt_dates[:2]):
                    standardized = standardize_date(date_str)
                    if standardized:
                        if i == 0:
                            data['barcode_issue_date'] = standardized
                        else:
                            data['barcode_expiry_date'] = standardized
            
            # Extract UID (various formats)
            uid_patterns = [
                r'U\.?I\.?D\.?\s*(?:No\.?)?\s*:?\s*(\d{8,})',
                r'UID\s*:?\s*(\d{8,})',
                r'(?:^|\s)(\d{9})(?:\s|$)',  # 9-digit number standalone
            ]
            for pattern in uid_patterns:
                uid_match = re.search(pattern, barcode_text, re.IGNORECASE)
                if uid_match:
                    data['barcode_uid'] = uid_match.group(1)
                    logger.info(f"  → UID: {data['barcode_uid']}")
                    break
            
            # Extract passport number (e.g., "A41268549")
            passport_match = re.search(r'[A-Z]\d{8,9}', barcode_text)
            if passport_match:
                data['barcode_passport_number'] = passport_match.group(0)
                logger.info(f"  → Passport: {data['barcode_passport_number']}")
            
            # Store raw barcode for reference
            data['barcode_raw'] = barcode_text
            
        except Exception as e:
            logger.error(f"Error parsing barcode: {e}")
            data['barcode_error'] = str(e)
        
        return data


class MRZParser:
    """Parse Machine Readable Zone (MRZ) data from visas."""

    @staticmethod
    def parse_mrz_date(date_str: str) -> Optional[str]:
        """Convert MRZ date format (YYMMDD) to ISO format (YYYY-MM-DD)."""
        if not date_str or len(date_str) != 6 or not date_str.isdigit():
            return None

        try:
            yy = int(date_str[0:2])
            mm = int(date_str[2:4])
            dd = int(date_str[4:6])

            if yy <= 40:
                year = 2000 + yy
            else:
                year = 1900 + yy

            datetime(year, mm, dd)
            return f"{year:04d}-{mm:02d}-{dd:02d}"
        except (ValueError, OverflowError):
            return None

    @staticmethod
    def parse_visa_mrz(mrz_line1: str, mrz_line2: str) -> Dict[str, Any]:
        """Parse visa MRZ (2 lines)."""
        data = {}

        if not mrz_line1 or not mrz_line2:
            return data

        line1 = re.sub(r'[^A-Z0-9<]', '', mrz_line1.upper())
        line2 = re.sub(r'[^A-Z0-9<]', '', mrz_line2.upper())

        if line1.startswith('V'):
            parts = line1[1:].split('<')
            if len(parts) >= 3:
                data['mrz_visa_type'] = parts[0].strip('<')
                data['mrz_country'] = parts[1].strip('<')

                name_parts = parts[2:]
                names = [p for p in name_parts if p]
                if len(names) >= 2:
                    surname = names[0].replace('<', ' ').strip()
                    given_names = ' '.join(names[1:]).replace('<', ' ').strip()
                    data['mrz_full_name'] = f"{surname}, {given_names}"

        if len(line2) >= 44:
            passport = line2[0:9].rstrip('<')
            if passport and passport != '0' * len(passport):
                data['mrz_passport_number'] = passport

            nationality = line2[10:13].rstrip('<')
            if nationality:
                data['mrz_nationality'] = nationality

            dob = MRZParser.parse_mrz_date(line2[13:19])
            if dob:
                data['mrz_date_of_birth'] = dob

            sex = line2[20] if len(line2) > 20 and line2[20] in ['M', 'F'] else None
            if sex:
                data['mrz_sex'] = sex

            expiry = MRZParser.parse_mrz_date(line2[21:27])
            if expiry:
                data['mrz_expiry_date'] = expiry

        return data


def extract_text_from_pdf_structured(pdf_path: str) -> Tuple[str, str, Dict[str, str]]:
    """
    Extract text from PDF with better structure preservation.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Tuple of (english_text, arabic_text, structured_fields)
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        
        # Extract text with layout preservation
        text_dict = page.get_text("dict")
        blocks = text_dict.get("blocks", [])
        
        all_text_lines = []
        
        # Process each block
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    line_text = ""
                    for span in line["spans"]:
                        line_text += span["text"] + " "
                    line_text = line_text.strip()
                    if line_text:
                        all_text_lines.append(line_text)
        
        # Join all text
        full_text = '\n'.join(all_text_lines)
        
        # Split into English and Arabic
        english_lines = []
        arabic_lines = []
        
        for line in all_text_lines:
            has_arabic = any('\u0600' <= char <= '\u06FF' for char in line)
            has_latin = any('a' <= char.lower() <= 'z' for char in line)
            
            if has_arabic:
                arabic_lines.append(line)
            if has_latin:
                english_lines.append(line)
        
        english_text = '\n'.join(english_lines)
        arabic_text = '\n'.join(arabic_lines)
        
        # Try to extract structured fields using regex patterns
        structured = {}
        
        # Common patterns for UAE visa
        patterns = {
            'visa_number': r'ENTRY\s+PERMIT\s+NO\.?\s*:?\s*(\d{3}/\d{4}/\d+)',
            'uid_number': r'U\.?I\.?D\.?\s*No\.?\s*:?\s*(\d{8,})',
            'date_of_issue': r'Date\s*&?\s*Place\s+of\s+Issue\s*:?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
            'valid_until': r'Valid\s+Until\s*:?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
            'date_of_birth': r'Date\s+of\s+Birth\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            'passport_number': r'Passport\s+No\.?\s*:?\s*(?:Normal\s*/\s*)?([A-Z]\d{8,9})',
        }
        
        for field, pattern in patterns.items():
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                structured[field] = match.group(1).strip()
                logger.info(f"  → Extracted {field}: {structured[field]}")
        
        doc.close()
        
        logger.info(f"Direct text extraction: {len(english_text)} chars English, {len(arabic_text)} chars Arabic")
        logger.info(f"Structured fields extracted: {len(structured)}")
        
        return english_text, arabic_text, structured
        
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return "", "", {}


def preprocess_image(img: Image.Image) -> Image.Image:
    """Preprocess image for better OCR results."""
    img = img.convert('L')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2)
    return img


def extract_text_with_ocr(image_path: str) -> Dict[str, Any]:
    """
    Extract text from image using PaddleOCR for both English and Arabic.
    
    Args:
        image_path: Path to image file
        
    Returns:
        Dictionary with extracted text and MRZ lines
    """
    try:
        # Lazy load OCR engines
        ocr_en, ocr_ar = get_ocr_engines()
        
        # Load image
        if os.path.exists(image_path):
            img = Image.open(image_path)
        else:
            img_data = base64.b64decode(image_path)
            img = Image.open(io.BytesIO(img_data))

        # Convert to RGB
        img_rgb = img.convert('RGB')

        # Preprocess for OCR
        img_preprocessed = preprocess_image(img_rgb)
        img_array = np.array(img_preprocessed)

        # Ensure 3-channel RGB
        if len(img_array.shape) == 2:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
        elif img_array.shape[2] == 4:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)

        # Run OCR
        logger.info("Running English OCR...")
        result_en = ocr_en.ocr(img_array)

        logger.info("Running Arabic OCR...")
        result_ar = ocr_ar.ocr(img_array)

        all_text_en = []
        all_text_ar = []
        mrz_lines = []
        mrz_with_pos = []

        # Process English results
        if result_en and result_en[0]:
            for line in result_en[0]:
                if line and len(line) >= 2 and line[1]:
                    text = line[1][0]
                    all_text_en.append(text)

                    # Detect MRZ lines
                    if '<<' in text or text.count('<') > 3:
                        bbox = line[0]
                        if bbox and len(bbox) >= 2:
                            y_pos = (bbox[0][1] + bbox[3][1]) / 2 if len(bbox) >= 4 else bbox[0][1]
                            mrz_with_pos.append((y_pos, text))

        # Process Arabic results
        if result_ar and result_ar[0]:
            for line in result_ar[0]:
                if line and len(line) >= 2 and line[1]:
                    text = line[1][0]
                    all_text_ar.append(text)

        # Sort MRZ lines
        if mrz_with_pos:
            mrz_with_pos.sort(key=lambda x: x[0])
            mrz_lines = [text for _, text in mrz_with_pos]

        return {
            'english_text': '\n'.join(all_text_en),
            'arabic_text': '\n'.join(all_text_ar),
            'lines_en': all_text_en,
            'lines_ar': all_text_ar,
            'mrz_lines': mrz_lines,
            'mrz_line1': mrz_lines[0] if len(mrz_lines) > 0 else None,
            'mrz_line2': mrz_lines[1] if len(mrz_lines) > 1 else None,
        }

    except Exception as e:
        logger.error(f"OCR extraction error: {e}", exc_info=True)
        return {
            'english_text': '',
            'arabic_text': '',
            'lines_en': [],
            'lines_ar': [],
            'mrz_lines': [],
            'mrz_line1': None,
            'mrz_line2': None,
            'error': str(e)
        }


def standardize_date(date_str: str) -> Optional[str]:
    """Standardize various date formats to YYYY-MM-DD."""
    if not date_str:
        return None

    date_str = str(date_str).strip().upper()

    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str

    # Format: DD-MM-YYYY or DD/MM/YYYY
    for sep in ['-', '/']:
        if sep in date_str:
            parts = date_str.split(sep)
            if len(parts) == 3:
                try:
                    # Try DD-MM-YYYY first
                    if len(parts[2]) == 4:
                        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                    # Try YYYY-MM-DD
                    elif len(parts[0]) == 4:
                        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                    else:
                        continue
                    
                    datetime(year, month, day)
                    return f"{year:04d}-{month:02d}-{day:02d}"
                except (ValueError, OverflowError):
                    pass

    # Format: DDMMMYYYY (e.g., 01JAN1980)
    if re.match(r'^\d{2}[A-Z]{3}\d{4}$', date_str):
        try:
            date_obj = datetime.strptime(date_str, '%d%b%Y')
            return date_obj.strftime('%Y-%m-%d')
        except ValueError:
            pass

    return None


def merge_extracted_data(llm_data: Dict[str, Any], mrz_data: Dict[str, Any], 
                         barcode_data: Dict[str, Any], structured_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge LLM, MRZ, barcode, and structured extracted data.
    Priority: Structured > Barcode > MRZ > LLM
    """
    merged = llm_data.copy()

    # Apply MRZ data
    if mrz_data.get('mrz_passport_number'):
        merged['passport_number'] = mrz_data['mrz_passport_number']
    if mrz_data.get('mrz_nationality'):
        merged['nationality'] = mrz_data['mrz_nationality']
    if mrz_data.get('mrz_date_of_birth'):
        merged['date_of_birth'] = mrz_data['mrz_date_of_birth']
    if mrz_data.get('mrz_expiry_date'):
        merged['date_of_expiry'] = mrz_data['mrz_expiry_date']
    if mrz_data.get('mrz_full_name') and not merged.get('full_name'):
        merged['full_name'] = mrz_data['mrz_full_name']

    # Apply barcode data
    if barcode_data.get('barcode_entry_permit'):
        merged['visa_number'] = barcode_data['barcode_entry_permit']
    if barcode_data.get('barcode_passport_number'):
        merged['passport_number'] = barcode_data['barcode_passport_number']
    if barcode_data.get('barcode_issue_date'):
        merged['date_of_issue'] = barcode_data['barcode_issue_date']
    if barcode_data.get('barcode_expiry_date'):
        merged['date_of_expiry'] = barcode_data['barcode_expiry_date']
    if barcode_data.get('barcode_uid'):
        merged['uid_number'] = barcode_data['barcode_uid']

    # Apply structured data (highest priority)
    for field, value in structured_data.items():
        if value:
            if field == 'valid_until':
                standardized = standardize_date(value)
                if standardized:
                    merged['date_of_expiry'] = standardized
            elif field in ['date_of_issue', 'date_of_birth']:
                standardized = standardize_date(value)
                if standardized:
                    merged[field] = standardized
            else:
                merged[field] = value

    # Store source data
    merged['mrz_data'] = mrz_data
    merged['barcode_data'] = barcode_data
    merged['structured_data'] = structured_data

    # Validation warnings
    warnings = []
    if merged.get('date_of_issue') and merged.get('date_of_expiry'):
        if merged['date_of_issue'] >= merged['date_of_expiry']:
            warnings.append("Issue date is after or equal to expiry date")

    if merged.get('date_of_expiry'):
        if merged['date_of_expiry'] < datetime.now().strftime('%Y-%m-%d'):
            warnings.append(f"Visa expired on {merged['date_of_expiry']}")

    critical_fields = ['visa_type', 'country', 'full_name', 'date_of_expiry']
    missing = [f for f in critical_fields if not merged.get(f)]
    if missing:
        warnings.append(f"Missing critical fields: {', '.join(missing)}")

    if warnings:
        merged['validation_warnings'] = warnings

    return merged


def extract_image_from_pdf(pdf_path: str) -> str:
    """Extract page from PDF as image."""
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]

        # Render page as image at high DPI
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        temp_path = f"temp_visa_{os.getpid()}.png"
        img.save(temp_path)

        doc.close()
        return temp_path

    except Exception as e:
        logger.error(f"Error extracting image from PDF: {e}", exc_info=True)
        return None


def process_visa_file(file_path: str) -> Dict[str, Any]:
    """
    Process a visa file using optimized extraction pipeline.
    
    Args:
        file_path: Path to the file to process.
        
    Returns:
        Dictionary with extracted visa information or error details.
    """
    temp_file = None

    try:
        from Utils.watson_config import llm_extraction

        extension = file_path.lower().split('.')[-1]
        
        english_text = ""
        arabic_text = ""
        mrz_line1 = None
        mrz_line2 = None
        barcode_data = {}
        structured_data = {}
        extraction_method = ""

        # Handle PDF files
        if extension == 'pdf':
            logger.info("=" * 60)
            logger.info("Processing PDF file...")
            
            # Step 1: Try barcode extraction
            logger.info("Step 1: Barcode extraction...")
            barcode_text = BarcodeParser.extract_barcode_from_pdf(file_path)
            if barcode_text:
                barcode_data = BarcodeParser.parse_visa_barcode(barcode_text)
                logger.info(f"✓ Barcode: {len(barcode_data)} fields")
            
            # Step 2: Direct text extraction with structure
            logger.info("Step 2: Direct text extraction...")
            english_text, arabic_text, structured_data = extract_text_from_pdf_structured(file_path)
            
            # Check if we have sufficient text
            has_sufficient_text = len(english_text) > 100
            
            if has_sufficient_text:
                logger.info(f"✓ Direct text: {len(english_text)} chars")
                extraction_method = "direct_text"
            else:
                logger.info("✗ Insufficient text, using OCR...")
                extraction_method = "ocr"
                
                image_path = extract_image_from_pdf(file_path)
                temp_file = image_path
                
                if not image_path:
                    return {"error": "Could not extract image from PDF"}
                
                ocr_result = extract_text_with_ocr(image_path)
                
                if 'error' in ocr_result:
                    return {"error": f"OCR error: {ocr_result['error']}"}
                
                english_text = ocr_result['english_text']
                arabic_text = ocr_result['arabic_text']
                mrz_line1 = ocr_result['mrz_line1']
                mrz_line2 = ocr_result['mrz_line2']
        
        # Handle image files
        elif extension in ['jpg', 'jpeg', 'png', 'bmp', 'tiff']:
            logger.info("=" * 60)
            logger.info("Processing image file...")
            extraction_method = "ocr"
            
            # Barcode detection
            logger.info("Step 1: Barcode extraction...")
            img = cv2.imread(file_path)
            if img is not None:
                barcode_text = BarcodeParser.detect_and_read_barcode(img)
                if barcode_text:
                    barcode_data = BarcodeParser.parse_visa_barcode(barcode_text)
            
            # OCR
            logger.info("Step 2: OCR...")
            ocr_result = extract_text_with_ocr(file_path)
            
            if 'error' in ocr_result:
                return {"error": f"OCR error: {ocr_result['error']}"}
            
            english_text = ocr_result['english_text']
            arabic_text = ocr_result['arabic_text']
            mrz_line1 = ocr_result['mrz_line1']
            mrz_line2 = ocr_result['mrz_line2']
        
        else:
            return {"error": f"Unsupported file format: {extension}"}

        logger.info(f"Text extracted: {len(english_text)} chars English")

        # Step 3: Parse MRZ
        mrz_data = {}
        if mrz_line1 and mrz_line2:
            logger.info("Step 3: MRZ parsing...")
            mrz_data = MRZParser.parse_visa_mrz(mrz_line1, mrz_line2)
            logger.info(f"✓ MRZ: {len(mrz_data)} fields")

        # Step 4: LLM extraction with improved prompt
        logger.info("Step 4: LLM extraction...")
        
        # Build context with all available data
        context_parts = [f"ENGLISH TEXT:\n{english_text}"]
        
        if arabic_text:
            context_parts.append(f"\nARABIC TEXT:\n{arabic_text}")
        
        if structured_data:
            context_parts.append(f"\nPRE-EXTRACTED FIELDS (use these if available):\n{json.dumps(structured_data, indent=2)}")
        
        if barcode_data and len(barcode_data) > 1:
            context_parts.append(f"\nBARCODE DATA:\n{json.dumps(barcode_data, indent=2)}")
        
        if mrz_line1 or mrz_line2:
            context_parts.append(f"\nMRZ LINES:\nLine 1: {mrz_line1 or 'Not detected'}\nLine 2: {mrz_line2 or 'Not detected'}")
        
        prompt = f"""Extract visa information from the following UAE eVisa document text.

{chr(10).join(context_parts)}

IMPORTANT INSTRUCTIONS:
1. Look for field labels followed by their values (e.g., "ENTRY PERMIT NO : 206/2025/87553014")
2. Dates may be in format DD-MM-YYYY or DD/MM/YYYY - convert ALL dates to YYYY-MM-DD
3. The document contains both English and Arabic text - prioritize English
4. If a field value is on a separate line from its label, look for it nearby
5. Common field patterns:
   - "ENTRY PERMIT NO : XXX" → visa_number
   - "U.I.D. No. : XXX" → uid_number
   - "Date & Place of Issue : DD-MM-YYYY Location" → date_of_issue and place_of_issue
   - "Valid Until : DD-MM-YYYY" → date_of_expiry
   - "Date of Birth : DD/MM/YYYY" → date_of_birth

Return ONLY a valid JSON object with these fields (use null for missing data):
{{
    "visa_type": "type of visa",
    "visa_number": "entry permit number",
    "country": "issuing country",
    "full_name": "full name in SURNAME, GIVEN_NAMES format",
    "nationality": "nationality",
    "passport_number": "passport number",
    "date_of_birth": "YYYY-MM-DD",
    "date_of_issue": "YYYY-MM-DD",
    "date_of_expiry": "YYYY-MM-DD",
    "place_of_birth": "place of birth",
    "place_of_issue": "place of issue",
    "profession": "profession/occupation",
    "uid_number": "U.I.D. number",
    "host_name": "sponsor/host name",
    "host_address": "sponsor/host address",
    "additional_info": "any other relevant information"
}}

CRITICAL: Return ONLY the JSON object, no explanations or markdown formatting."""

        response = llm_extraction.generate(prompt)
        result_text = response['results'][0]['generated_text'].strip()

        # Clean up response
        if result_text.startswith("```"):
            parts = result_text.split("```")
            if len(parts) >= 2:
                result_text = parts[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', result_text, re.DOTALL)
        if json_match:
            result_text = json_match.group(0)

        result_text = result_text.strip()

        if not result_text:
            return {"error": "LLM returned empty response"}

        visa_data = json.loads(result_text)

        # Standardize dates
        date_fields = ['date_of_birth', 'date_of_issue', 'date_of_expiry']
        for field in date_fields:
            if visa_data.get(field):
                standardized = standardize_date(visa_data[field])
                if standardized:
                    visa_data[field] = standardized

        # Add raw data
        visa_data['raw_english_text'] = english_text
        visa_data['raw_arabic_text'] = arabic_text
        visa_data['mrz_line1'] = mrz_line1
        visa_data['mrz_line2'] = mrz_line2
        visa_data['extraction_method'] = extraction_method

        # Merge all data sources
        final_data = merge_extracted_data(visa_data, mrz_data, barcode_data, structured_data)

        # Add confidence indicator
        critical_fields_filled = sum([
            bool(final_data.get('visa_type')),
            bool(final_data.get('country')),
            bool(final_data.get('full_name')),
            bool(final_data.get('passport_number')),
            bool(final_data.get('date_of_expiry'))
        ])
        final_data['extraction_confidence'] = f"{critical_fields_filled}/5 critical fields"
        
        # Track data sources
        final_data['data_sources_used'] = []
        if structured_data:
            final_data['data_sources_used'].append('structured_regex')
        if barcode_data and len(barcode_data) > 1:
            final_data['data_sources_used'].append('barcode')
        if mrz_data:
            final_data['data_sources_used'].append('mrz')
        final_data['data_sources_used'].append(extraction_method)

        logger.info("=" * 60)
        logger.info(f"✓ Extraction complete: {critical_fields_filled}/5 critical fields")
        logger.info("=" * 60)

        return final_data

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        logger.error(f"LLM response was: {result_text if 'result_text' in locals() else 'N/A'}")
        return {"error": f"Failed to parse JSON: {str(e)}"}
    except Exception as e:
        logger.error(f"Error processing visa file: {e}", exc_info=True)
        return {"error": f"Processing error: {str(e)}"}
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass


def generate_visa_html(visas_data: List[Dict[str, Any]]) -> str:
    """Generate simple, clean HTML display for extracted visa information."""
    if not visas_data:
        return """
        <div style="padding: 20px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; text-align: center; color: #6b7280;">
            No visa information available
        </div>
        """

    html_parts = []

    for i, visa in enumerate(visas_data, 1):
        if "error" in visa:
            html_parts.append(f"""
            <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 20px; margin-bottom: 16px;">
                <h3 style="color: #dc2626; margin: 0 0 8px 0; font-size: 16px; font-weight: 600;">
                    ❌ Error - {visa.get('filename', 'Unknown')}
                </h3>
                <p style="color: #991b1b; margin: 0; font-size: 14px;">{visa['error']}</p>
            </div>
            """)
        else:
            # Determine status color
            is_expired = False
            if visa.get('validation_warnings'):
                for warning in visa['validation_warnings']:
                    if 'expired' in warning.lower():
                        is_expired = True
                        break
            
            status_color = "#dc2626" if is_expired else "#059669"
            status_text = "EXPIRED" if is_expired else "VALID"
            
            html_parts.append(f"""
            <div style="background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 24px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="border-bottom: 2px solid #e5e7eb; padding-bottom: 16px; margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                        <h3 style="color: #111827; margin: 0; font-size: 18px; font-weight: 600;">
                            🛂 {visa.get('filename', 'Visa Information')}
                        </h3>
                        <span style="background: {status_color}; color: white; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;">
                            {status_text}
                        </span>
                    </div>
                </div>

                <!-- Visa Details -->
                <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500; width: 40%;">Visa Type</td>
                        <td style="padding: 12px 8px; color: #111827; font-weight: 500;">{visa.get('visa_type') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Entry Permit Number</td>
                        <td style="padding: 12px 8px; color: #111827; font-weight: 600;">{visa.get('visa_number') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">U.I.D. Number</td>
                        <td style="padding: 12px 8px; color: #111827; font-weight: 600;">{visa.get('uid_number') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Country</td>
                        <td style="padding: 12px 8px; color: #111827;">{visa.get('country') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Full Name</td>
                        <td style="padding: 12px 8px; color: #111827; font-weight: 600;">{visa.get('full_name') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Nationality</td>
                        <td style="padding: 12px 8px; color: #111827;">{visa.get('nationality') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Passport Number</td>
                        <td style="padding: 12px 8px; color: #111827; font-weight: 600;">{visa.get('passport_number') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Date of Birth</td>
                        <td style="padding: 12px 8px; color: #111827;">{visa.get('date_of_birth') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Place of Birth</td>
                        <td style="padding: 12px 8px; color: #111827;">{visa.get('place_of_birth') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Profession</td>
                        <td style="padding: 12px 8px; color: #111827;">{visa.get('profession') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Date of Issue</td>
                        <td style="padding: 12px 8px; color: #111827;">{visa.get('date_of_issue') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Place of Issue</td>
                        <td style="padding: 12px 8px; color: #111827;">{visa.get('place_of_issue') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Valid Until (Expiry)</td>
                        <td style="padding: 12px 8px; color: {status_color}; font-weight: 600;">{visa.get('date_of_expiry') or 'N/A'}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Host/Sponsor</td>
                        <td style="padding: 12px 8px; color: #111827;">{visa.get('host_name') or 'N/A'}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 8px; color: #6b7280; font-weight: 500;">Host Address</td>
                        <td style="padding: 12px 8px; color: #111827;">{visa.get('host_address') or 'N/A'}</td>
                    </tr>
                </table>

                <!-- Warnings if any -->
                {f'''
                <div style="margin-top: 16px; padding: 12px; background: #fef3c7; border: 1px solid #fbbf24; border-radius: 6px;">
                    <p style="margin: 0; color: #92400e; font-size: 13px; font-weight: 600;">⚠️ Warnings:</p>
                    <ul style="margin: 8px 0 0 0; padding-left: 20px; color: #92400e; font-size: 13px;">
                        {"".join([f"<li>{w}</li>" for w in visa['validation_warnings']])}
                    </ul>
                </div>
                ''' if visa.get('validation_warnings') else ''}
            </div>
            """)

    return f"""
    <div style="max-width: 800px; margin: 0 auto; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <h2 style="color: #111827; margin-bottom: 24px; font-size: 24px; font-weight: 700;">Visa Information</h2>
        {"".join(html_parts)}
    </div>
    """


def process_multiple_visa_files(file_paths: List[str]) -> List[Dict[str, Any]]:
    """Process multiple visa files and return results."""
    results = []

    for file_path in file_paths:
        try:
            result = process_visa_file(file_path)
            result["filename"] = os.path.basename(file_path)
            results.append(result)
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            results.append({
                "error": f"Error processing file: {str(e)}",
                "filename": os.path.basename(file_path)
            })

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extract visa information using intelligent text extraction + barcode + LLM")
    parser.add_argument("files", nargs="+", help="File paths to process")
    args = parser.parse_args()

    results = process_multiple_visa_files(args.files)

    # Print JSON results
    print(json.dumps(results, indent=2, ensure_ascii=False))

    # Generate HTML output
    html_output = generate_visa_html(results)
    with open("visa_results.html", "w", encoding="utf-8") as f:
        f.write(html_output)

    print("\nVisa information extracted and saved to visa_results.html")