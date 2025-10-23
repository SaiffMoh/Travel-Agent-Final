import os
import traceback
import zxingcpp
import re
import datetime
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

def get_lower_left(image):
    """Extract the lower left quadrant where MRZ is typically located"""
    height, width = image.shape[:2]
    return image[height // 2:, :width // 2]


def detect_barcode(image):
    """Detect and crop barcode/MRZ region from passport image"""
    original = image.copy()
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Compute gradient (highlight barcode-like structures)
    gradX = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
    gradY = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=0, dy=1, ksize=-1)
    gradient = cv2.subtract(gradX, gradY)
    gradient = cv2.convertScaleAbs(gradient)

    # Blur and threshold
    blurred = cv2.blur(gradient, (9, 9))
    _, thresh = cv2.threshold(blurred, 225, 255, cv2.THRESH_BINARY)

    # Morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 7))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    # Remove small blobs
    closed = cv2.erode(closed, None, iterations=4)
    closed = cv2.dilate(closed, None, iterations=4)

    # Find contours
    cnts, _ = cv2.findContours(closed.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        c = sorted(cnts, key=cv2.contourArea, reverse=True)[0]
        x, y, w, h = cv2.boundingRect(c)

        # Expand the bounding box by a larger margin for better results
        margin_x = int(w * 0.2)
        margin_y = int(h * 0.3)
        x_exp = max(x - margin_x, 0)
        y_exp = max(y - margin_y, 0)
        w_exp = min(w + 2 * margin_x, original.shape[1] - x_exp)
        h_exp = min(h + 2 * margin_y, original.shape[0] - y_exp)

        # Crop from the original image
        cropped = original[y_exp:y_exp + h_exp, x_exp:x_exp + w_exp]
        return cropped

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


def parse_mrz(mrz_line: str) -> dict:
    """Parse MRZ line and extract passport information"""
    mrz = mrz_line.strip()

    # Find passport number (9 chars) + check digit, nationality (3), DOB(6)+check, sex, expiry(6)+check
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

    # Names are between the first 5 characters (P<XXX) and the passport-number match start
    names_start = 5
    names_end = m.start()
    names_section = mrz[names_start:names_end]
    # Standard MRZ: surname<<given1<given2...
    parts = names_section.split('<<', 1)
    surname = parts[0].replace('<', '') if parts else ''
    given_raw = parts[1] if len(parts) > 1 else ''
    given_parts = [p for p in given_raw.split('<') if p]
    given_names = ' '.join(given_parts)

    # Dates
    birth_date = format_date(birth_raw)
    expiry_date = format_date(expiry_raw)

    # Compute issued date: expiry year minus 7, same month, day after expiry day
    try:
        expiry_dt = datetime.datetime.strptime(expiry_date, "%Y-%m-%d")
        issued_year = expiry_dt.year - 7
        issued_day = expiry_dt.day + 1
        # Handle month overflow
        try:
            issued_dt = expiry_dt.replace(year=issued_year, day=issued_day)
        except ValueError:
            # If day exceeds month, roll over to next month
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


def process_passport_file(file_path: str) -> dict:
    """
    Process a single passport file (PDF or image) and extract MRZ data
    
    Args:
        file_path: Path to the passport file
        
    Returns:
        Dictionary with extracted passport information or error details
    """
    try:
        passport = None
        extension = file_path.split('.')[-1].lower()
        
        if extension == 'pdf':
            import fitz  # PyMuPDF
            
            doc = fitz.open(file_path)
            
            # Convert first page to image
            if len(doc) > 0:
                page = doc[0]
                pix = page.get_pixmap(dpi=600)
                
                # Convert pixmap to numpy array
                img_data = pix.samples
                passport = np.frombuffer(img_data, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                
                # Convert RGBA to BGR if needed
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

        # Process the image
        passport = get_lower_left(passport)
        passport = detect_barcode(passport)
        
        # Upscale for better OCR
        scale_factor = 2
        passport = cv2.resize(passport, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
        
        # Read barcodes/MRZ
        barcodes = zxingcpp.read_barcodes(passport)
        
        if not barcodes:
            return {"error": "No MRZ barcode detected in passport image"}
        
        # Try to parse the first valid barcode
        for barcode in barcodes:
            try:
                text = barcode.text
                parsed = parse_mrz(text)
                
                if "error" not in parsed:
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

