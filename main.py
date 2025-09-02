from fastapi import FastAPI, HTTPException, UploadFile, Form  # Added Form
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from langgraph.errors import GraphRecursionError
from typing import List
import traceback
import logging
from Utils.question_to_html import question_to_html
from graph import create_travel_graph
from Models.ChatRequest import ChatRequest
from Models.ExtractedInfo import ExtractedInfo
from Models.FlightResult import FlightResult
from Models.ConversationStore import conversation_store
from Nodes.invoice_extraction_node import invoice_extraction_node
from fastapi.responses import HTMLResponse
from pathlib import Path
import shutil
import uuid
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

required_keys = ["OPENAI_API_KEY", "AMADEUS_CLIENT_ID", "AMADEUS_CLIENT_SECRET"]
for key in required_keys:
    value = os.getenv(key)
    if not value:
        print(f"{key}: MISSING")

app = FastAPI(
    title="Flight Search Chatbot API",
    description="AI-powered flight search assistant with thread-based conversations"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define directory structure
DATA_DIR = Path("data")
UPLOAD_DIR = DATA_DIR / "uploads"
PDF_DIR = UPLOAD_DIR / "pdfs"
JSON_DIR = UPLOAD_DIR / "json_outputs"

# Create directories if they don't exist
for directory in [DATA_DIR, UPLOAD_DIR, PDF_DIR, JSON_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

graph = create_travel_graph().compile()

@app.get("/")
async def root():
    return {"message": "Flight Search Chatbot API v2.0 is running"}

@app.get("/health")
async def health():
    missing_keys = [key for key in required_keys if not os.getenv(key)]
    if missing_keys:
        return {
            "status": "warning",
            "message": f"Missing API keys: {', '.join(missing_keys)}",
            "missing_keys": missing_keys
        }
    return {"status": "healthy", "message": "All API keys configured"}

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """Handles the conversation for flight search and visa queries using thread_id and user_msg."""
    
    try:
        if not request.thread_id:
            print("ERROR: Missing thread_id")
            raise HTTPException(status_code=400, detail="thread_id is required")
        
        user_message = request.user_msg.strip()
        if not user_message:
            print("ERROR: Empty user message")
            raise HTTPException(status_code=400, detail="user_msg cannot be empty")

        missing_keys = [key for key in required_keys if not os.getenv(key)]
        if missing_keys:
            print(f"ERROR: Missing API keys: {missing_keys}")
            raise HTTPException(
                status_code=500,
                detail=f"Missing API keys: {', '.join(missing_keys)}"
            )

        conversation_history = conversation_store.get_conversation(request.thread_id)
        print(f"✓ Got conversation history: {len(conversation_history)} messages")
        
        conversation_store.add_message(request.thread_id, "user", user_message)
        updated_conversation = conversation_store.get_conversation(request.thread_id)
        print(f"✓ Updated conversation: {len(updated_conversation)} messages")

        previous_state = conversation_store.get_state(request.thread_id) or {}
        
        state = {
            "thread_id": request.thread_id,
            "conversation": updated_conversation,
            "current_message": user_message,
            "user_message": user_message,
            "needs_followup": True,
            "info_complete": False,
            "trip_type": "round trip",
            "node_trace": [],
            "followup_question": None,
            "current_node": "llm_conversation",
            "followup_count": previous_state.get("followup_count", 0),
            "request_type": previous_state.get("request_type", "flights"),
            "travel_search_completed": previous_state.get("travel_search_completed", False),
            "visa_info_html": None,
            "invoice_uploaded": previous_state.get("invoice_uploaded", False),
            "invoice_pdf_path": previous_state.get("invoice_pdf_path"),
            "extracted_invoice_data": previous_state.get("extracted_invoice_data"),
            "invoice_html": previous_state.get("invoice_html")
        }
        
        travel_fields = ["departure_date", "origin", "destination", "cabin_class", "duration", "travel_packages_html"]
        for field in travel_fields:
            if field in previous_state:
                state[field] = previous_state[field]

        if graph is None:
            print("ERROR: Graph was not compiled at startup")
            raise HTTPException(status_code=500, detail="Graph compilation failed")

        print(f"Executing graph with state: {state}")
        result = graph.invoke(state)
        
        print("✓ LangGraph execution completed")
        
        try:
            print("Result keys:", list(result.keys()))
            if result.get("travel_packages"):
                print(f"✓ travel_packages present: {len(result.get('travel_packages', []))}")
            if result.get("travel_packages_html"):
                print(f"✓ travel_packages_html present: {len(result.get('travel_packages_html', []))}")
            if result.get("visa_info_html"):
                print("✓ visa_info_html present")
            if result.get("package_summary"):
                print("✓ package_summary present")
            if result.get("extracted_invoice_data"):
                print("✓ extracted_invoice_data present")
            if result.get("invoice_html"):
                print("✓ invoice_html present")
            print(f"Travel search completed: {result.get('travel_search_completed', False)}")
        except Exception as _:
            print("(debug) unable to print result keys")

        state_to_save = {
            "departure_date": result.get("departure_date"),
            "origin": result.get("origin"),
            "destination": result.get("destination"),
            "cabin_class": result.get("cabin_class"),
            "duration": result.get("duration"),
            "followup_count": result.get("followup_count", 0),
            "request_type": result.get("request_type", "flights"),
            "travel_search_completed": result.get("travel_search_completed", False),
            "travel_packages_html": result.get("travel_packages_html"),
            "invoice_uploaded": result.get("invoice_uploaded", False),
            "invoice_pdf_path": result.get("invoice_pdf_path"),
            "extracted_invoice_data": result.get("extracted_invoice_data"),
            "invoice_html": result.get("invoice_html")
        }
        conversation_store.save_state(request.thread_id, state_to_save)

        extracted_info = ExtractedInfo(
            departure_date=result.get("departure_date"),
            origin=result.get("origin"),
            destination=result.get("destination"),
            cabin_class=result.get("cabin_class"),
            trip_type=result.get("trip_type"),
            duration=result.get("duration")
        )

        if result.get("visa_info_html"):
            print("✓ Returning visa_info_html")
            conversation_store.add_message(request.thread_id, "assistant", "Visa requirements provided")
            return result["visa_info_html"]

        if result.get("needs_followup", True):
            assistant_message = result.get("followup_question", "Could you provide more details about your flight?")
            conversation_store.add_message(request.thread_id, "assistant", assistant_message)
            html_content = question_to_html(assistant_message, extracted_info)
            return html_content

        if result.get("travel_packages_html"):
            print(f"✓ Returning {len(result['travel_packages_html'])} travel packages (HTML)")
            state_to_save["travel_search_completed"] = True
            conversation_store.save_state(request.thread_id, state_to_save)
            assistant_message = "Here are your travel packages:"
            conversation_store.add_message(request.thread_id, "assistant", assistant_message)
            return result["travel_packages_html"]

        flights = []
        if result.get("formatted_results"):
            flights = [
                FlightResult(
                    price=str(f.get("price", "N/A")),
                    currency=str(f.get("currency", "USD")),
                    search_date=str(f.get("search_date", "")) or None,
                    outbound={
                        "airline": str(f.get("outbound", {}).get("airline", "N/A")),
                        "flight_number": str(f.get("outbound", {}).get("flight_number", "N/A")),
                        "departure_airport": str(f.get("outbound", {}).get("departure_airport", "N/A")),
                        "arrival_airport": str(f.get("outbound", {}).get("arrival_airport", "N/A")),
                        "departure_time": str(f.get("outbound", {}).get("departure_time", "N/A")),
                        "arrival_time": str(f.get("outbound", {}).get("arrival_time", "N/A")),
                        "duration": str(f.get("outbound", {}).get("duration", "N/A")),
                        "stops": int(f.get("outbound", {}).get("stops", 0)) if f.get("outbound", {}).get("stops") is not None else None,
                        "layovers": [str(x) for x in (f.get("outbound", {}).get("layovers") or [])],
                    },
                    return_leg={
                        "airline": str(f.get("return_leg", {}).get("airline", "N/A")),
                        "flight_number": str(f.get("return_leg", {}).get("flight_number", "N/A")),
                        "departure_airport": str(f.get("return_leg", {}).get("departure_airport", "N/A")),
                        "arrival_airport": str(f.get("return_leg", {}).get("arrival_airport", "N/A")),
                        "return_time": str(f.get("return_leg", {}).get("departure_time", "N/A")),
                        "arrival_time": str(f.get("return_leg", {}).get("arrival_time", "N/A")),
                        "duration": str(f.get("return_leg", {}).get("duration", "N/A")),
                        "stops": int(f.get("return_leg", {}).get("stops", 0)) if f.get("return_leg", {}).get("stops") is not None else None,
                        "layovers": [str(x) for x in (f.get("return_leg", {}).get("layovers") or [])],
                    } if f.get("return_leg") else None,
                )
                for f in result.get("formatted_results", [])
            ]
            print(f"returned {len(flights)} flight results")

        assistant_message = result.get("summary", "Here are your flight options:")
        conversation_store.add_message(request.thread_id, "assistant", assistant_message)
        return flights

    except HTTPException as he:
        print(f"HTTPException: {he.detail}")
        traceback.print_exc()
        raise
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Internal server error while processing request"
        )

@app.post("/api/reset/{thread_id}")
async def reset_conversation(thread_id: str):
    """Reset conversation history for a specific thread"""
    print(f"Resetting conversation for thread: {thread_id}")
    conversation_store.clear_conversation(thread_id)
    conversation_store.clear_state(thread_id)
    return {"message": f"Conversation for thread {thread_id} has been reset"}

@app.get("/api/threads")
async def get_active_threads():
    """Get all active conversation threads"""
    threads = conversation_store.get_all_threads()
    print(f"Getting active threads: {len(threads)} found")
    return {"threads": threads, "count": len(threads)}

@app.post("/api/invoices/upload", response_class=HTMLResponse)
async def upload_invoice(files: List[UploadFile], thread_id: str = Form(...)):
    """
    Handle multiple PDF uploads for invoice processing and return ONLY HTML.
    """
    if not files:
        return """
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-red-600">No files uploaded. Please upload at least one PDF.</p>
        </div>
        """

    all_html = []
    
    for file in files:
        temp_file_path = None
        try:
            if not file.filename.lower().endswith('.pdf'):
                all_html.append(f"""
                <div class="p-4 bg-red-50 border border-red-200 rounded-lg mb-4">
                    <p class="text-red-600">File '{file.filename}' is not a PDF. Only PDF files are supported.</p>
                </div>
                """)
                continue
            
            # Create temporary file
            filename = f"{uuid.uuid4()}_{file.filename}"
            temp_file_path = PDF_DIR / filename
            
            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Set up state for processing
            state = {
                "thread_id": thread_id,
                "current_message": f"Processing uploaded invoice: {file.filename}",
                "user_message": f"Processing uploaded invoice: {file.filename}",
                "needs_followup": True,
                "followup_question": None,
                "current_node": "invoice_extraction",
                "invoice_uploaded": True,
                "invoice_pdf_path": str(temp_file_path),
                "extracted_invoice_data": None,
                "invoice_html": None
            }
            
            # Process through the graph
            result = graph.invoke(state)
            
            # Extract ONLY the HTML
            invoice_html = result.get("invoice_html", f"""
            <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p class="text-yellow-600">Invoice '{file.filename}' processed but no data extracted.</p>
            </div>
            """)
            
            # Add file header if multiple files
            if len(files) > 1:
                all_html.append(f"""
                <div class="mb-6">
                    <h3 class="text-lg font-semibold text-gray-800 mb-3">File: {file.filename}</h3>
                    {invoice_html}
                </div>
                """)
            else:
                all_html.append(invoice_html)

        except Exception as e:
            logging.error(f"Exception processing {file.filename}: {e}")
            all_html.append(f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-lg mb-4">
                <p class="text-red-600">Error processing '{file.filename}': {str(e)}</p>
            </div>
            """)
        finally:
            # Clean up temporary file
            if temp_file_path and temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except Exception as e:
                    logging.error(f"Error cleaning up file {temp_file_path}: {e}")

    # Return concatenated HTML for all files
    return "".join(all_html)