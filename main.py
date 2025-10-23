from fastapi import FastAPI, HTTPException, UploadFile, Form  # Added Form
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from langgraph.errors import GraphRecursionError
from typing import List
import traceback
import logging
from Utils.question_to_html import question_to_html
from Utils.passport_decoder import generate_passport_html, process_passport_file
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
PASSPORT_DIR = UPLOAD_DIR / "passports"


# Create directories if they don't exist
for directory in [DATA_DIR, UPLOAD_DIR, PDF_DIR, JSON_DIR, PASSPORT_DIR]:
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


    
from fastapi.responses import HTMLResponse
from Nodes.flight_inquiry_node import create_flight_inquiry_graph
import traceback
import logging

# Add this after your existing graph creation
flight_inquiry_graph = create_flight_inquiry_graph().compile()

@app.post("/api/flight-inquiry", response_class=HTMLResponse)
async def flight_inquiry_endpoint(request: ChatRequest):
    """
    Handle general flight inquiries - takes origin, destination, and date
    Returns HTML for frontend display
    """
    try:
        if not request.thread_id:
            return """
            <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p class="text-red-600">Error: thread_id is required</p>
            </div>
            """
        
        user_message = request.user_msg.strip()
        if not user_message:
            return """
            <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p class="text-red-600">Error: user_msg cannot be empty</p>
            </div>
            """

        # Check API keys
        required_keys = ["AMADEUS_CLIENT_ID", "AMADEUS_CLIENT_SECRET", "OPENAI_API_KEY"]
        missing_keys = [key for key in required_keys if not os.getenv(key)]
        if missing_keys:
            return f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p class="text-red-600">Missing API keys: {', '.join(missing_keys)}</p>
            </div>
            """

        # Set up state for flight inquiry
        state = {
            "thread_id": request.thread_id,
            "current_message": user_message,
            "user_message": user_message,
            "needs_followup": True,
            "ready_to_search": False,
            "flight_options": [],
            "search_error": None,
            "flight_inquiry_html": None
        }

        print(f"DEBUG: Initial state setup complete")
        print(f"Processing flight inquiry: {user_message}")
        
        # Execute the flight inquiry graph
        result = flight_inquiry_graph.invoke(state)
        
        print(f"DEBUG: Graph execution complete")
        print(f"DEBUG: Final result keys: {list(result.keys())}")
        
        # Enhanced debugging - check flight_options in result
        flight_options = result.get("flight_options", [])
        print(f"DEBUG: flight_options in result: {len(flight_options)} flights")
        if flight_options:
            print(f"DEBUG: First flight option: {flight_options[0] if flight_options else 'None'}")
        
        # Check for HTML content in various possible keys
        html_content = None
        possible_html_keys = ["flight_inquiry_html", "html_content", "formatted_html", "result_html"]
        
        for key in possible_html_keys:
            if key in result and result[key]:
                html_content = result[key]
                print(f"DEBUG: Found HTML content in key '{key}'")
                break
        
        # If no HTML found in expected keys, check all string values for HTML-like content
        if not html_content:
            print("DEBUG: No HTML content found in expected keys, checking all string values")
            for key, value in result.items():
                if isinstance(value, str) and ("<div" in value or "<html" in value or "class=" in value):
                    html_content = value
                    print(f"DEBUG: Found HTML-like content in key '{key}': {value[:100]}...")
                    break
        
        # Handle specific error cases
        if result.get("search_error"):
            error_msg = result["search_error"]
            print(f"DEBUG: Search error detected: {error_msg}")
            html_content = f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <h3 class="text-lg font-semibold text-red-700 mb-2">Flight Search Error</h3>
                <p class="text-red-600 mb-2">We encountered an issue while searching for flights:</p>
                <p class="text-sm text-red-500 bg-red-100 p-2 rounded">{error_msg}</p>
                <p class="text-sm text-gray-600 mt-2">Please try again later or contact support if the problem persists.</p>
            </div>
            """
        
        # Handle case where we have flight options but no HTML was generated
        elif flight_options and not html_content:
            print(f"DEBUG: Found {len(flight_options)} flights but no HTML generated, creating manual HTML")
            
            flights_html = ""
            for i, flight in enumerate(flight_options[:5]):  # Show first 5 flights
                flights_html += f"""
                <div class="bg-white border rounded-lg p-4 mb-3 shadow-sm">
                    <div class="flex justify-between items-start mb-2">
                        <div class="flex-1">
                            <span class="font-medium text-lg">{flight.get('airline', 'N/A')} {flight.get('flight_number', '')}</span>
                            <span class="text-sm text-gray-600 ml-2">({flight.get('booking_class', 'Economy').title()})</span>
                        </div>
                        <div class="text-right">
                            <span class="text-xl font-bold text-green-600">{flight.get('price', 'N/A')} {flight.get('currency', 'EUR')}</span>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <span class="font-medium">From:</span> {flight.get('from', 'N/A')}
                            <br>
                            <span class="font-medium">Departure:</span> {flight.get('departure_time', 'N/A')[:16].replace('T', ' ')}
                        </div>
                        <div>
                            <span class="font-medium">To:</span> {flight.get('to', 'N/A')}
                            <br>
                            <span class="font-medium">Arrival:</span> {flight.get('arrival_time', 'N/A')[:16].replace('T', ' ')}
                        </div>
                    </div>
                    <div class="mt-2 text-sm text-gray-600">
                        <span class="font-medium">Duration:</span> {flight.get('duration', 'N/A')} | 
                        <span class="font-medium">Stops:</span> {flight.get('stops', 0)}
                    </div>
                </div>
                """
            
            html_content = f"""
            <div class="p-6 bg-white border rounded-lg shadow-sm">
                <h3 class="text-xl font-semibold text-gray-800 mb-4">Flight Options</h3>
                <div class="mb-4 p-3 bg-blue-50 rounded">
                    <div class="grid grid-cols-3 gap-4 text-sm">
                        <div><span class="font-medium">From:</span> {result.get('origin', 'N/A')}</div>
                        <div><span class="font-medium">To:</span> {result.get('destination', 'N/A')}</div>
                        <div><span class="font-medium">Date:</span> {result.get('departure_date', 'N/A')}</div>
                    </div>
                </div>
                <div class="space-y-3">
                    {flights_html}
                </div>
                {f'<p class="text-sm text-gray-600 mt-4">Showing {min(5, len(flight_options))} of {len(flight_options)} available flights</p>' if len(flight_options) > 5 else ''}
            </div>
            """
        
        # Handle case where extraction was successful but no flights found
        elif result.get("origin") and result.get("destination") and result.get("departure_date"):
            origin = result["origin"]
            destination = result["destination"]
            date = result["departure_date"]
            
            if not html_content:
                html_content = f"""
                <div class="p-6 bg-blue-50 border border-blue-200 rounded-lg">
                    <h3 class="text-lg font-semibold text-blue-700 mb-3">Flight Search Summary</h3>
                    <div class="space-y-2 mb-4">
                        <p><span class="font-medium">From:</span> {origin}</p>
                        <p><span class="font-medium">To:</span> {destination}</p>
                        <p><span class="font-medium">Date:</span> {date}</p>
                    </div>
                    <div class="bg-yellow-100 border border-yellow-300 rounded p-3">
                        <p class="text-yellow-700">No flights found or search service temporarily unavailable.</p>
                        <p class="text-sm text-yellow-600 mt-1">Please try again later or modify your search criteria.</p>
                        <details class="mt-2">
                            <summary class="text-xs cursor-pointer">Debug Info</summary>
                            <pre class="text-xs mt-1 bg-yellow-50 p-2 rounded overflow-auto">
Flight options count: {len(flight_options)}
Available result keys: {', '.join(result.keys())}
                            </pre>
                        </details>
                    </div>
                </div>
                """
        
        # Handle case where followup is needed
        elif result.get("needs_followup") and result.get("followup_question"):
            question = result["followup_question"]
            html_content = f"""
            <div class="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <h3 class="text-lg font-semibold text-blue-700 mb-2">More Information Needed</h3>
                <p class="text-blue-600">{question}</p>
            </div>
            """
        
        # Final fallback
        if not html_content:
            print("DEBUG: No HTML content generated, using fallback")
            html_content = f"""
            <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <h3 class="text-lg font-semibold text-yellow-700 mb-2">Processing Flight Inquiry</h3>
                <p class="text-yellow-600 mb-2">Your request: "{user_message}"</p>
                <p class="text-sm text-gray-600">The system processed your request but couldn't generate the display.</p>
                <details class="mt-3">
                    <summary class="text-xs text-gray-500 cursor-pointer">Debug Info</summary>
                    <pre class="text-xs text-gray-400 mt-1 bg-gray-100 p-2 rounded overflow-auto">
Available keys: {', '.join(result.keys())}
Flight options: {len(flight_options)}
                    </pre>
                </details>
            </div>
            """
        
        print(f"DEBUG: Returning HTML content of length: {len(html_content)}")
        return html_content

    except Exception as e:
        print(f"Error in flight inquiry endpoint: {e}")
        traceback.print_exc()
        return f"""
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <h3 class="text-lg font-semibold text-red-700 mb-2">System Error</h3>
            <p class="text-red-600 mb-2">An unexpected error occurred while processing your flight inquiry.</p>
            <details class="mt-2">
                <summary class="text-sm text-red-500 cursor-pointer">Error Details</summary>
                <pre class="text-xs text-red-400 mt-1 bg-red-100 p-2 rounded overflow-auto">{str(e)}</pre>
            </details>
            <p class="text-sm text-gray-600 mt-3">Please try again or contact support if the problem persists.</p>
        </div>
        """
# main.py - FastAPI endpoint for cheapest date search
from fastapi.responses import HTMLResponse
from Nodes.cheapest_date_node import create_cheapest_date_graph
from Nodes.get_access_token_node import get_access_token_node  # Import the existing node
import traceback
import logging
import os

# Initialize the graph
cheapest_date_graph = create_cheapest_date_graph().compile()

@app.post("/api/cheapest-date-search", response_class=HTMLResponse)
async def cheapest_date_search_endpoint(request: ChatRequest):
    """
    Handle cheapest date flight searches - takes origin, destination, date range, and nonStop preference
    Returns HTML for frontend display
    """
    try:
        # Validate required fields
        if not request.thread_id:
            return """
            <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p class="text-red-600">Error: thread_id is required</p>
            </div>
            """

        user_message = request.user_msg.strip()
        if not user_message:
            return """
            <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p class="text-red-600">Error: user_msg cannot be empty</p>
            </div>
            """

        # Check API keys
        required_keys = ["AMADEUS_CLIENT_ID", "AMADEUS_CLIENT_SECRET", "OPENAI_API_KEY"]
        missing_keys = [key for key in required_keys if not os.getenv(key)]
        if missing_keys:
            return f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p class="text-red-600">Missing API keys: {', '.join(missing_keys)}</p>
            </div>
            """

        # Set up initial state for cheapest date search with dedicated fields
        state = {
            # Thread / conversation
            "thread_id": request.thread_id,
            "current_message": user_message,
            "user_message": user_message,

            # Cheapest date search specific fields
            "cheapest_date_origin": None,
            "cheapest_date_destination": None,
            "cheapest_date_departure_range": None,
            "cheapest_date_normalized_range": None,
            "cheapest_date_non_stop": None,
            "cheapest_date_results": [],
            "cheapest_date_error": None,
            "cheapest_date_html": None,
            "needs_followup": True,
            "followup_question": None,

            # Access token will be added by get_access_token_node
            "access_token": None
        }

        print(f"DEBUG: Initial state setup complete")
        print(f"Processing cheapest date search: {user_message}")

        # First get the access token
        state = get_access_token_node(state)

        if not state.get("access_token"):
            return """
            <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p class="text-red-600">Error: Could not obtain Amadeus access token. Please check your API credentials.</p>
            </div>
            """

        print(f"DEBUG: Successfully obtained access token")

        # Execute the cheapest date search graph
        result = cheapest_date_graph.invoke(state)

        print(f"DEBUG: Graph execution complete")
        print(f"DEBUG: Final result keys: {list(result.keys())}")

        # Check for cheapest dates in result
        cheapest_dates = result.get("cheapest_date_results", [])
        print(f"DEBUG: cheapest_dates in result: {len(cheapest_dates)} results")
        if cheapest_dates:
            print(f"DEBUG: First cheapest date result: {cheapest_dates[0] if cheapest_dates else 'None'}")

        # Check for HTML content in various possible keys
        html_content = None
        possible_html_keys = ["cheapest_date_html", "html_content", "formatted_html", "result_html"]

        for key in possible_html_keys:
            if key in result and result[key]:
                html_content = result[key]
                print(f"DEBUG: Found HTML content in key '{key}'")
                break

        # If no HTML found in expected keys, check all string values for HTML-like content
        if not html_content:
            print("DEBUG: No HTML content found in expected keys, checking all string values")
            for key, value in result.items():
                if isinstance(value, str) and ("<div" in value or "<html" in value or "class=" in value):
                    html_content = value
                    print(f"DEBUG: Found HTML-like content in key '{key}': {value[:100]}...")
                    break

        # Handle specific error cases
        if result.get("cheapest_date_error"):
            error_msg = result["cheapest_date_error"]
            print(f"DEBUG: Search error detected: {error_msg}")
            html_content = f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <h3 class="text-lg font-semibold text-red-700 mb-2">Cheapest Date Search Error</h3>
                <p class="text-red-600 mb-2">We encountered an issue while searching for cheapest dates:</p>
                <p class="text-sm text-red-500 bg-red-100 p-2 rounded">{error_msg}</p>
                <p class="text-sm text-gray-600 mt-2">Please try again later or contact support if the problem persists.</p>
            </div>
            """

        # Handle case where we have cheapest dates but no HTML was generated
        elif cheapest_dates and not html_content:
            print(f"DEBUG: Found {len(cheapest_dates)} cheapest dates but no HTML generated, creating manual HTML")

            dates_html = ""
            for i, date_option in enumerate(cheapest_dates[:10]):  # Show first 10 dates
                dates_html += f"""
                <div class="bg-white border rounded-lg p-4 mb-3 shadow-sm">
                    <div class="flex justify-between items-start mb-2">
                        <div class="flex-1">
                            <span class="font-medium text-lg">{date_option.get('departure_date', 'N/A')}</span>
                            <span class="text-sm text-gray-600 ml-2">({date_option.get('return_date', 'One way')})</span>
                        </div>
                        <div class="text-right">
                            <span class="text-xl font-bold text-green-600">{date_option.get('price', {}).get('total', 'N/A')} {date_option.get('price', {}).get('currency', 'EUR')}</span>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <span class="font-medium">From:</span> {date_option.get('origin', 'N/A')}
                            <br>
                            <span class="font-medium">To:</span> {date_option.get('destination', 'N/A')}
                        </div>
                        <div>
                            <span class="font-medium">Non-stop:</span> {'Yes' if result.get('cheapest_date_non_stop') else 'No'}
                            <br>
                            <span class="font-medium">Trip Type:</span> Round Trip
                        </div>
                    </div>
                </div>
                """

            html_content = f"""
            <div class="p-6 bg-white border rounded-lg shadow-sm">
                <h3 class="text-xl font-semibold text-gray-800 mb-4">Cheapest Flight Dates</h3>
                <div class="mb-4 p-3 bg-blue-50 rounded">
                    <div class="grid grid-cols-3 gap-4 text-sm">
                        <div><span class="font-medium">From:</span> {result.get('cheapest_date_origin', 'N/A')}</div>
                        <div><span class="font-medium">To:</span> {result.get('cheapest_date_destination', 'N/A')}</div>
                        <div><span class="font-medium">Date Range:</span> {result.get('cheapest_date_departure_range', 'N/A')}</div>
                    </div>
                </div>
                <div class="space-y-3">
                    {dates_html}
                </div>
                {f'<p class="text-sm text-gray-600 mt-4">Showing {min(10, len(cheapest_dates))} of {len(cheapest_dates)} available dates</p>' if len(cheapest_dates) > 10 else ''}
            </div>
            """

        # Handle case where extraction was successful but no dates found
        elif result.get("cheapest_date_origin") and result.get("cheapest_date_destination") and result.get("cheapest_date_departure_range"):
            origin = result["cheapest_date_origin"]
            destination = result["cheapest_date_destination"]
            date_range = result["cheapest_date_departure_range"]

            if not html_content:
                html_content = f"""
                <div class="p-6 bg-blue-50 border border-blue-200 rounded-lg">
                    <h3 class="text-lg font-semibold text-blue-700 mb-3">Cheapest Date Search Summary</h3>
                    <div class="space-y-2 mb-4">
                        <p><span class="font-medium">From:</span> {origin}</p>
                        <p><span class="font-medium">To:</span> {destination}</p>
                        <p><span class="font-medium">Date Range:</span> {date_range}</p>
                        <p><span class="font-medium">Non-stop preference:</span> {'Required' if result.get('cheapest_date_non_stop') else 'Flexible'}</p>
                    </div>
                    <div class="bg-yellow-100 border border-yellow-300 rounded p-3">
                        <p class="text-yellow-700">No cheapest dates found or search service temporarily unavailable.</p>
                        <p class="text-sm text-yellow-600 mt-1">Please try again later or modify your search criteria.</p>
                        <details class="mt-2">
                            <summary class="text-xs cursor-pointer">Debug Info</summary>
                            <pre class="text-xs mt-1 bg-yellow-50 p-2 rounded overflow-auto">
Cheapest dates count: {len(cheapest_dates)}
Available result keys: {', '.join(result.keys())}
                            </pre>
                        </details>
                    </div>
                </div>
                """

        # Handle case where followup is needed
        elif result.get("needs_followup") and result.get("followup_question"):
            question = result["followup_question"]
            html_content = f"""
            <div class="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <h3 class="text-lg font-semibold text-blue-700 mb-2">More Information Needed</h3>
                <p class="text-blue-600">{question}</p>
            </div>
            """

        # Final fallback
        if not html_content:
            print("DEBUG: No HTML content generated, using fallback")
            html_content = f"""
            <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <h3 class="text-lg font-semibold text-yellow-700 mb-2">Processing Cheapest Date Search</h3>
                <p class="text-yellow-600 mb-2">Your request: "{user_message}"</p>
                <p class="text-sm text-gray-600">The system processed your request but couldn't generate the display.</p>
                <details class="mt-3">
                    <summary class="text-xs text-gray-500 cursor-pointer">Debug Info</summary>
                    <pre class="text-xs text-gray-400 mt-1 bg-gray-100 p-2 rounded overflow-auto">
Available keys: {', '.join(result.keys())}
Cheapest dates: {len(cheapest_dates)}
                    </pre>
                </details>
            </div>
            """

        print(f"DEBUG: Returning HTML content of length: {len(html_content)}")
        return html_content
    except Exception as e:
        print(f"Error in cheapest date search endpoint: {e}")
        traceback.print_exc()
        return f"""
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <h3 class="text-lg font-semibold text-red-700 mb-2">System Error</h3>
            <p class="text-red-600 mb-2">An unexpected error occurred while processing your cheapest date search.</p>
            <details class="mt-2">
                <summary class="text-sm text-red-500 cursor-pointer">Error Details</summary>
                <pre class="text-xs text-red-400 mt-1 bg-red-100 p-2 rounded overflow-auto">{str(e)}</pre>
            </details>
            <p class="text-sm text-gray-600 mt-3">Please try again or contact support if the problem persists.</p>
        </div>
        """
    
# Add this endpoint after your existing endpoints
@app.post("/api/passports/upload", response_class=HTMLResponse)
async def upload_passports(files: List[UploadFile], thread_id: str = Form(...)):
    """
    Handle multiple passport uploads (PDF or image files) and return HTML with extracted information.
    Uploaded files are saved to PASSPORT_DIR and not deleted so they remain available on disk.
    """
    try:
        # Validate thread_id similar to other endpoints
        if not thread_id:
            return """
            <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p class="text-red-600">Error: thread_id is required</p>
            </div>
            """

        if not files:
            return """
            <div class="p-6 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p class="text-yellow-700 text-center">No passports uploaded</p>
            </div>
            """

        # Record upload action in conversation store
        conversation_store.add_message(thread_id, "user", f"Uploaded {len(files)} passport file(s)")

        passports_data = []
        saved_paths = []

        for file in files:
            temp_file_path = None
            try:
                # Validate file extension
                extension = file.filename.lower().split('.')[-1]
                if extension not in ['pdf', 'jpg', 'jpeg', 'png', 'bmp', 'tiff']:
                    passports_data.append({
                        "error": f"Unsupported file format: {extension}",
                        "filename": file.filename
                    })
                    continue

                # Create permanent file in PASSPORT_DIR (do not delete)
                filename = f"{uuid.uuid4()}_{file.filename}"
                temp_file_path = PASSPORT_DIR / filename

                # Save uploaded file
                with open(temp_file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)

                logging.info(f"Saved passport file: {temp_file_path}")
                saved_paths.append(str(temp_file_path))

                # Process the passport file
                passport_info = process_passport_file(str(temp_file_path))

                # Add filename and saved path to the result
                passport_info["filename"] = file.filename
                passport_info["saved_path"] = str(temp_file_path)
                passports_data.append(passport_info)

                if "error" not in passport_info:
                    logging.info(f"Successfully extracted passport info from {file.filename}")
                else:
                    logging.warning(f"Failed to extract passport info from {file.filename}: {passport_info['error']}")

            except Exception as e:
                logging.error(f"Exception processing passport {file.filename}: {e}")
                traceback.print_exc()
                passports_data.append({
                    "error": f"Processing error: {str(e)}",
                    "filename": file.filename
                })
            finally:
                # Do NOT remove saved passport files. Keep them on disk per request.
                pass

        # Generate HTML from all passport data
        html_content = generate_passport_html(passports_data)

        # Save state to conversation store so frontend can reference later
        state_to_save = {
            "passports_uploaded": True,
            "passports_data": passports_data,
            "passport_html": html_content,
            "passport_file_paths": saved_paths
        }
        conversation_store.save_state(thread_id, state_to_save)

        # Add assistant message summarizing result
        summary_msg = "Passport data extracted" if any("error" not in p for p in passports_data) else "Passport extraction completed with errors"
        conversation_store.add_message(thread_id, "assistant", summary_msg)

        return html_content

    except Exception as e:
        logging.error(f"Unexpected error in passports upload endpoint: {e}")
        traceback.print_exc()
        return f"""
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <h3 class="text-lg font-semibold text-red-700 mb-2">System Error</h3>
            <p class="text-red-600 mb-2">An unexpected error occurred while processing your passport upload.</p>
            <details class="mt-2">
                <summary class="text-sm text-red-500 cursor-pointer">Error Details</summary>
                <pre class="text-xs text-red-400 mt-1 bg-red-100 p-2 rounded overflow-auto">{str(e)}</pre>
            </details>
            <p class="text-sm text-gray-600 mt-3">Please try again or contact support if the problem persists.</p>
        </div>
        """