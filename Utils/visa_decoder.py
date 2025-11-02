"""
Utils/visa_decoder.py
Visa information extraction from images, PDFs, and Word documents.
Similar to passport_decoder but extracts visa-specific fields.
"""
import os
import base64
import logging
import json
from typing import Dict, Any, List
from openai import OpenAI
import fitz  # PyMuPDF
from PIL import Image
import io

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_image_from_pdf(pdf_path: str) -> str:
    """Extract the first image from a PDF and convert it to base64."""
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        image_list = page.get_images(full=True)

        if not image_list:
            return None

        xref = image_list[0][0]
        base_image = doc.extract_image(xref)
        image_bytes = base_image["image"]

        return base64.b64encode(image_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"Error extracting image from PDF: {e}")
        return None

def extract_image_from_docx(docx_path: str) -> str:
    """Extract the first image from a Word document and convert it to base64."""
    try:
        import docx
        from docx.opc.constants import RELATIONSHIP_TYPE as RT

        doc = docx.Document(docx_path)

        for rel in doc.part.rels.values():
            if "image" in rel.target_ref:
                image_bytes = rel.target_part.blob
                return base64.b64encode(image_bytes).decode('utf-8')

        return None
    except Exception as e:
        logger.error(f"Error extracting image from DOCX: {e}")
        return None

def image_to_base64(image_path: str) -> str:
    """Convert an image file to base64."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Error converting image to base64: {e}")
        return None

def process_visa_file(file_path: str) -> Dict[str, Any]:
    """
    Process a visa file (image, PDF, or Word document) and extract information using GPT-4 Vision.

    Args:
        file_path: Path to the file to process.

    Returns:
        Dictionary with extracted visa information or error details.
    """
    try:
        extension = file_path.lower().split('.')[-1]
        base64_image = None

        if extension in ['jpg', 'jpeg', 'png', 'bmp', 'tiff']:
            base64_image = image_to_base64(file_path)
        elif extension == 'pdf':
            base64_image = extract_image_from_pdf(file_path)
        elif extension in ['doc', 'docx']:
            base64_image = extract_image_from_docx(file_path)
        else:
            return {"error": f"Unsupported file format: {extension}"}

        if not base64_image:
            return {"error": "Could not extract image from file"}

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Extract visa information from this image. Return ONLY a valid JSON object with these exact fields (use null for missing/unclear data):
{
    "visa_type": "type of visa (tourist, business, work, student, etc.)",
    "visa_number": "visa number or control number",
    "country": "issuing country",
    "full_name": "full name of visa holder",
    "nationality": "nationality of visa holder",
    "passport_number": "passport number linked to visa",
    "date_of_birth": "date of birth (YYYY-MM-DD format)",
    "date_of_issue": "visa issue date (YYYY-MM-DD format)",
    "date_of_expiry": "visa expiry date (YYYY-MM-DD format)",
    "valid_from": "valid from date (YYYY-MM-DD format)",
    "valid_until": "valid until date (YYYY-MM-DD format)",
    "entries": "number of entries allowed (single, multiple, or number)",
    "duration_of_stay": "allowed duration of stay",
    "place_of_issue": "place where visa was issued",
    "purpose_of_visit": "purpose of travel/visit",
    "additional_info": "any other relevant information"
}
Be precise and only include information clearly visible in the image."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1000
        )

        result_text = response.choices[0].message.content.strip()

        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]

        visa_data = json.loads(result_text)
        return visa_data

    except Exception as e:
        logger.error(f"Error processing visa file: {e}")
        return {"error": f"Processing error: {str(e)}"}

def generate_visa_html(visas_data: List[Dict[str, Any]]) -> str:
    """
    Generate an HTML display for extracted visa information.

    Args:
        visas_data: List of visa data dictionaries.

    Returns:
        HTML string for display.
    """
    if not visas_data:
        return """
        <div class="p-6 bg-gray-50 border border-gray-200 rounded-lg">
            <p class="text-gray-600 text-center">No visa information available</p>
        </div>
        """

    html_parts = []

    for i, visa in enumerate(visas_data, 1):
        if "error" in visa:
            html_parts.append(f"""
            <div class="bg-red-50 border border-red-200 rounded-lg p-6 mb-4">
                <h3 class="text-lg font-semibold text-red-700 mb-2">
                    ❌ Visa {i}: {visa.get('filename', 'Unknown')}
                </h3>
                <p class="text-red-600">{visa['error']}</p>
            </div>
            """)
        else:
            html_parts.append(f"""
            <div class="bg-white border border-gray-200 rounded-lg shadow-sm p-6 mb-4">
                <h3 class="text-xl font-bold text-green-700 mb-4">
                    🛂 Visa {i}: {visa.get('filename', 'Visa Information')}
                </h3>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="space-y-3">
                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Visa Type</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('visa_type') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Visa Number</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('visa_number') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Issuing Country</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('country') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Full Name</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('full_name') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Nationality</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('nationality') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Passport Number</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('passport_number') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Date of Birth</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('date_of_birth') or 'N/A'}</p>
                        </div>
                    </div>

                    <div class="space-y-3">
                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Issue Date</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('date_of_issue') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Expiry Date</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('date_of_expiry') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Valid From</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('valid_from') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Valid Until</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('valid_until') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Entries Allowed</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('entries') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Duration of Stay</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('duration_of_stay') or 'N/A'}</p>
                        </div>

                        <div class="border-b pb-2">
                            <p class="text-xs text-gray-500 uppercase">Place of Issue</p>
                            <p class="text-sm font-medium text-gray-800">{visa.get('place_of_issue') or 'N/A'}</p>
                        </div>
                    </div>
                </div>

                {f'''
                <div class="mt-4 p-3 bg-blue-50 rounded">
                    <p class="text-xs text-gray-500 uppercase mb-1">Purpose of Visit</p>
                    <p class="text-sm text-gray-700">{visa.get('purpose_of_visit')}</p>
                </div>
                '''
                if visa.get('purpose_of_visit') else ''}

                {f'''
                <div class="mt-4 p-3 bg-gray-50 rounded">
                    <p class="text-xs text-gray-500 uppercase mb-1">Additional Information</p>
                    <p class="text-sm text-gray-700">{visa.get('additional_info')}</p>
                </div>
                '''
                if visa.get('additional_info') else ''}
            </div>
            """)

    return f"""
    <div class="max-w-4xl mx-auto p-4">
        <h2 class="text-2xl font-bold text-gray-800 mb-6">Visa Information</h2>
        {"".join(html_parts)}
    </div>
    """

def process_multiple_visa_files(file_paths: List[str]) -> List[Dict[str, Any]]:
    """
    Process multiple visa files and return a list of results.

    Args:
        file_paths: List of file paths to process.

    Returns:
        List of visa data dictionaries or error messages.
    """
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

    parser = argparse.ArgumentParser(description="Extract visa information from files.")
    parser.add_argument("files", nargs="+", help="File paths to process")
    args = parser.parse_args()

    results = process_multiple_visa_files(args.files)
    html_output = generate_visa_html(results)

    with open("visa_results.html", "w", encoding="utf-8") as f:
        f.write(html_output)

    print("Visa information extracted and saved to visa_results.html")
