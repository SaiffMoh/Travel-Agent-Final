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
            "NationalID": str,
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
            return {"error": "No MRZ barcode detected in passport image"}
       
        for barcode in barcodes:
            try:
                text = barcode.text
                print('hola text',text)
                parsed = parse_mrz(text)
                print('hola parsed',parsed)
               
                if "error" not in parsed:
                    # Return JSON in the required format
                    return {
                        "NameInPassport": parsed.get('full_name', ''),
                        "PassportNum": parsed.get('passport_number', ''),
                        "ExpiryDate": parsed.get('expiry_date', ''),
                        "NationalID": parsed.get('nationality', '')
                    }
            except Exception as e:
                logger.error(f"Error parsing barcode: {e}")
                continue
       
        return {"error": "Could not parse MRZ data from detected barcodes"}
       
    except Exception as e:
        logger.error(f"Error processing passport file {file_path}: {e}")
        traceback.print_exc()
        return {"error": f"Processing error: {str(e)}"}
