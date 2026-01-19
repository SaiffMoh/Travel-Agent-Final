"""
Utils/ocr_engine.py
Centralized OCR engine supporting both development and production environments.
- Dev mode: Uses PaddleOCR models from HuggingFace (via RapidOCR wrapper)
- Prod mode: Uses VLMM API for OCR
"""
import os
import io
import base64
import logging
import traceback
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
ENV_MODE = os.getenv("env", "dev").lower()  # "dev" or "prod"
VLMM_API_BASE = "https://ibm-models.elsewedy.com:4005/v1"
VLMM_MODEL = "unsloth/Qwen2.5-VL-72B-Instruct-bnb-4bit"

# Cache for RapidOCR engine
_rapid_ocr_engine = None


def get_rapidocr_engine():
    """
    Lazy load RapidOCR engine.
    RapidOCR is a lightweight wrapper around PaddleOCR models from HuggingFace.
    It downloads PaddleOCR detection and recognition models automatically.
    
    Models used:
    - Detection: PaddleOCR's PP-OCRv4 detection model
    - Recognition: PaddleOCR's PP-OCRv4 recognition model
    - Angle classification: PaddleOCR's angle classifier
    """
    global _rapid_ocr_engine
    
    if _rapid_ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            
            logger.info("Initializing RapidOCR with PaddleOCR models (first time only)...")
            
            # Initialize RapidOCR - it will automatically download PaddleOCR models
            # from HuggingFace/GitHub on first run and cache them
            _rapid_ocr_engine = RapidOCR()
            
            logger.info("RapidOCR initialized successfully with PaddleOCR models")
        except Exception as e:
            logger.error(f"Failed to initialize RapidOCR: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
    
    return _rapid_ocr_engine


def ocr_with_rapidocr_paddle(image_bytes: bytes) -> str:
    """
    Perform OCR using RapidOCR (PaddleOCR models from HuggingFace).
    
    RapidOCR uses ONNX Runtime to run PaddleOCR models efficiently without
    the full PaddlePaddle framework, avoiding dependency conflicts.
    
    Args:
        image_bytes: Image data as bytes
        
    Returns:
        Extracted text
    """
    try:
        from PIL import Image
        import numpy as np
        import cv2
        
        # Get cached engine
        engine = get_rapidocr_engine()
        
        # Convert bytes to PIL Image
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Convert to numpy array for OpenCV processing
        image_np = np.array(image)
        
        # Apply preprocessing to improve OCR accuracy
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
        
        # Try multiple preprocessing strategies
        preprocessing_methods = [
            ("original", image_np),
            ("gray", gray),
        ]
        
        # Adaptive threshold for varying lighting
        try:
            thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, 11, 2
            )
            preprocessing_methods.append(("adaptive_thresh", thresh))
        except:
            pass
        
        # Bilateral filter to reduce noise while preserving edges
        try:
            bilateral = cv2.bilateralFilter(gray, 9, 75, 75)
            preprocessing_methods.append(("bilateral", bilateral))
        except:
            pass
        
        # Increase contrast with CLAHE
        try:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            clahe_img = clahe.apply(gray)
            preprocessing_methods.append(("clahe", clahe_img))
        except:
            pass
        
        all_text_lines = []
        best_result = ""
        max_chars = 0
        
        for method_name, img_to_process in preprocessing_methods:
            try:
                # Perform OCR
                result, elapse = engine(img_to_process)
                
                if result is None:
                    continue
                
                # Extract text from results
                # result is a list of [bbox, text, confidence]
                text_lines = []
                for line in result:
                    if len(line) >= 2:
                        text = line[1]  # The recognized text
                        confidence = line[2] if len(line) >= 3 else 0
                        
                        # Only include text with reasonable confidence
                        if text.strip() and confidence > 0.3:
                            text_lines.append(text)
                
                extracted = "\n".join(text_lines)
                
                # Keep track of all results
                all_text_lines.extend(text_lines)
                
                # Track the best result (most characters extracted)
                if len(extracted) > max_chars:
                    max_chars = len(extracted)
                    best_result = extracted
                    
                logger.info(f"RapidOCR ({method_name}) extracted {len(extracted)} characters, {len(text_lines)} lines")
                
            except Exception as e:
                logger.warning(f"RapidOCR ({method_name}) attempt failed: {e}")
                continue
        
        # Combine unique lines from all methods
        if all_text_lines:
            # Remove duplicates while preserving order
            seen = set()
            unique_lines = []
            for line in all_text_lines:
                line_clean = line.strip()
                # Keep line if not seen before
                if line_clean and line_clean not in seen:
                    seen.add(line_clean)
                    unique_lines.append(line)
            
            combined_text = "\n".join(unique_lines)
            
            logger.info(f"RapidOCR final: {len(combined_text)} characters from {len(unique_lines)} unique lines")
            return combined_text
        else:
            logger.warning("RapidOCR returned no results from any method")
            return ""
        
    except Exception as e:
        logger.error(f"RapidOCR failed: {e}")
        logger.error(f"RapidOCR traceback: {traceback.format_exc()}")
        return ""
    except Exception as e:
        logger.error(f"RapidOCR failed: {e}")
        logger.error(f"RapidOCR traceback: {traceback.format_exc()}")
        return ""

def ocr_with_vlmm(image_bytes: bytes, custom_prompt: Optional[str] = None) -> str:
    """
    Perform OCR using VLMM API (prod mode).
    
    Args:
        image_bytes: Image data as bytes
        custom_prompt: Optional custom prompt for specific extraction needs
        
    Returns:
        Extracted text
    """
    try:
        from openai import OpenAI
        
        # Encode image to base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        
        # Initialize OpenAI client for VLMM
        client = OpenAI(
            base_url=VLMM_API_BASE,
            api_key="EMPTY"
        )
        
        # Default prompt if none provided
        if custom_prompt is None:
            custom_prompt = "Extract ALL text from this image. Return ONLY the text content, preserving layout and structure. Include all numbers, dates, names, and details."
        
        # Request OCR from VLMM
        response = client.chat.completions.create(
            model=VLMM_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": custom_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        }
                    ],
                }
            ],
            max_tokens=2000,
        )
        
        extracted_text = response.choices[0].message.content
        logger.info(f"VLMM OCR extracted {len(extracted_text)} characters")
        return extracted_text
        
    except Exception as e:
        logger.error(f"VLMM OCR failed: {e}")
        raise  # Fail completely in prod as per requirement


def ocr_image(image_bytes: bytes, custom_prompt: Optional[str] = None, document_type: str = "general") -> str:
    """
    Main OCR function that automatically selects the appropriate OCR engine based on environment.
    
    Args:
        image_bytes: Image data as bytes
        custom_prompt: Optional custom prompt for VLMM (used in prod mode)
        document_type: Type of document being processed (for logging)
        
    Returns:
        Extracted text
    """
    logger.info(f"OCR processing {document_type} document in {ENV_MODE.upper()} mode")
    
    if ENV_MODE == "prod":
        logger.info("Using VLMM OCR in production mode")
        return ocr_with_vlmm(image_bytes, custom_prompt)
    else:
        # In dev mode, use RapidOCR (PaddleOCR models via ONNX)
        logger.info("Using RapidOCR (PaddleOCR models) in development mode")
        text = ocr_with_rapidocr_paddle(image_bytes)
        
        return text


# Predefined prompts for different document types
INVOICE_OCR_PROMPT = "Extract ALL text from this invoice image. Return ONLY the text content, preserving layout and structure. Include all numbers, dates, names, and details."

VISA_OCR_PROMPT = """Extract ALL text from this visa/entry permit document image with precise layout preservation.

IMPORTANT:
1. Preserve the exact layout and spacing of the document
2. Keep field labels together with their values (e.g., "ENTRY PERMIT NO : 206/2025/87553014")
3. Maintain line breaks as they appear in the document
4. Extract ALL visible text including:
   - Document title (e.g., "ENTRY PERMIT", "VISA")
   - Entry/Visa permit numbers
   - U.I.D. numbers
   - Passport numbers and types
   - Full names (surname and given names)
   - Dates (issue date, expiry date, birth date)
   - Nationality and gender
   - Profession/occupation
   - Sponsor/host information
   - Any addresses or contact information
   - Duration and number of entries
   - All Arabic text (if present)

Return ONLY the extracted text preserving the original structure. Do not summarize or interpret."""

PASSPORT_OCR_PROMPT = """Extract ALL text from this passport image with special focus on the Machine Readable Zone (MRZ).

CRITICAL - MRZ EXTRACTION:
1. The MRZ is typically at the BOTTOM of the passport as 2-3 lines of text
2. MRZ lines start with 'P<' and contain characters like '<' throughout
3. Each MRZ line is exactly 44 characters long
4. Extract COMPLETE MRZ lines without breaks - preserve all characters including '<' symbols
5. Keep MRZ lines together and continuous (e.g., 'P<EGYEMARA<<AHMED<HESHAM<AHMED<YOUSSEF<<<<<<')

EXAMPLE MRZ FORMAT:
Line 1: P<EGYEMARA<<AHMED<HESHAM<AHMED<YOUSSEF<<<<<<
Line 2: A412685499EGY9810204M3204290<<<<<<<<<<<<<<00

EXTRACT ALL TEXT INCLUDING:
- Passport holder's full name
- Passport number
- Nationality
- Date of birth
- Gender
- Issue and expiry dates
- ALL MRZ characters (complete lines, not fragments)

Return the text preserving structure with MRZ lines kept intact."""


def ocr_invoice(image_bytes: bytes) -> str:
    """OCR specifically for invoice documents."""
    return ocr_image(image_bytes, INVOICE_OCR_PROMPT, "invoice")


def ocr_visa(image_bytes: bytes) -> str:
    """OCR specifically for visa documents."""
    return ocr_image(image_bytes, VISA_OCR_PROMPT, "visa")


def ocr_passport(image_bytes: bytes) -> str:
    """OCR specifically for passport documents."""
    return ocr_image(image_bytes, PASSPORT_OCR_PROMPT, "passport")