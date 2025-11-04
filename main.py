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
from Nodes.visa_rag_node import visa_rag_node
from pathlib import Path
import shutil
import uuid
import json
from Nodes.web_search_node import web_search_node
from Nodes.greeting_conversation_node import greeting_conversation_node

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
    """
    Unified chat endpoint that handles all conversation types.
    Visa RAG is now checked FIRST for all tools before routing to specific flows.
    """
    
    try:
        # ===== VALIDATION =====
        if not request.thread_id:
            print("ERROR: Missing thread_id")
            raise HTTPException(status_code=400, detail="thread_id is required")
        
        user_message = request.user_msg.strip()
        if not user_message:
            print("ERROR: Empty user message")
            raise HTTPException(status_code=400, detail="user_msg cannot be empty")

        # Get previous state once at the start (used by multiple flows)
        previous_state = conversation_store.get_state(request.thread_id) or {}

        # ===== CHECK FOR VISA INQUIRY FIRST (Universal across all tools) =====
        from Utils.routing import detect_visa_inquiry
        
        # Build state for visa detection
        temp_state = {
            "thread_id": request.thread_id,
            "current_message": user_message,
            "user_message": user_message,
            "destination": previous_state.get("destination")
        }
        
        is_visa_inquiry, detected_country = detect_visa_inquiry(temp_state)
        
        if is_visa_inquiry:
            print(f"🔍 Visa inquiry detected (universal check) for: {detected_country or 'country TBD'}")
            conversation_store.add_message(request.thread_id, "user", user_message)
            
            state = {
                "thread_id": request.thread_id,
                "user_message": user_message,
                "current_message": user_message,
                "detected_visa_country": detected_country,
                "destination": temp_state.get("destination"),
                "visa_info_html": None
            }
            
            result = visa_rag_node(state)
            
            logger.info(f"Visa RAG completed for {detected_country or 'unspecified country'}")
            conversation_store.add_message(request.thread_id, "assistant", "Visa requirements provided")
            
            state_to_save = {
                "visa_info_html": result.get("visa_info_html"),
                "detected_visa_country": detected_country
            }
            conversation_store.save_state(request.thread_id, state_to_save)
            
            return result["visa_info_html"]

        # ===== ROUTING BASED ON tool_id (if not visa inquiry) =====
        tool_id = request.tool_id
        
        # 1. WEB SEARCH ROUTING
        if tool_id == "web_search":
            print(f"🌐 Web search request detected for thread: {request.thread_id}")
            print(f"Query: {user_message}")
            
            conversation_store.add_message(request.thread_id, "user", user_message)
            
            state = {
                "thread_id": request.thread_id,
                "user_message": user_message,
                "current_message": user_message,
                "web_search_result": None,
                "web_search_html": None,
                "web_search_error": None
            }
            
            result = web_search_node(state)
            
            if result.get("web_search_error"):
                logger.error(f"Web search error: {result['web_search_error']}")
                conversation_store.add_message(request.thread_id, "assistant", "Web search failed")
                return result["web_search_html"]
            
            logger.info("Web search completed successfully")
            conversation_store.add_message(request.thread_id, "assistant", "Web search results provided")
            
            state_to_save = {
                "web_search_result": result.get("web_search_result"),
                "web_search_html": result.get("web_search_html")
            }
            conversation_store.save_state(request.thread_id, state_to_save)
            
            return result["web_search_html"]
        
        # 2. GREETING/CASUAL CONVERSATION ROUTING (Default)
        elif tool_id is None or tool_id == "greeting":
            print(f"💬 Greeting/casual conversation request for thread: {request.thread_id}")
            print(f"Message: {user_message}")
            
            conversation_history = conversation_store.get_conversation(request.thread_id)
            conversation_store.add_message(request.thread_id, "user", user_message)
            
            state = {
                "thread_id": request.thread_id,
                "user_message": user_message,
                "current_message": user_message,
                "conversation": conversation_history,
                "greeting_response": None,
                "greeting_html": None,
                "greeting_error": None
            }
            
            result = greeting_conversation_node(state)
            
            if result.get("greeting_error"):
                logger.error(f"Greeting conversation error: {result['greeting_error']}")
                conversation_store.add_message(request.thread_id, "assistant", "Conversation error")
                return result["greeting_html"]
            
            logger.info("Greeting conversation completed successfully")
            assistant_message = result.get("greeting_response", "I'm here to help!")
            conversation_store.add_message(request.thread_id, "assistant", assistant_message)
            
            state_to_save = {
                "greeting_response": result.get("greeting_response"),
                "greeting_html": result.get("greeting_html")
            }
            conversation_store.save_state(request.thread_id, state_to_save)
            
            return result["greeting_html"]
        
        # 3. AMADEUS TRAVEL FLOW ROUTING
        elif tool_id == "amadeus":
            print(f"✈️ Amadeus travel search request for thread: {request.thread_id}")
            print(f"Query: {user_message}")
            
            # Check for required API keys for Amadeus flow
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

            # Use the previous_state already retrieved at the start
            # ===== NEW CODE: DETECT BOOKING INTENT BEFORE GRAPH EXECUTION =====
            from Utils.routing import detect_booking_intent
            
            is_booking, package_id = detect_booking_intent({
                "current_message": user_message,
                "user_message": user_message,
                "booking_in_progress": previous_state.get("booking_in_progress", False)
            })
            
            if is_booking and package_id:
                logger.info(f"🎯 Pre-graph booking detection: Package {package_id} selected")
            # ===== END NEW CODE =====
            
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
            
            # BOOKING-RELATED STATE (CRITICAL!)
            "travel_packages": previous_state.get("travel_packages", []),
            "passport_uploaded": previous_state.get("passport_uploaded", False),
            "passport_data": previous_state.get("passport_data", []),
            "visa_uploaded": previous_state.get("visa_uploaded", False),
            "visa_data": previous_state.get("visa_data", []),
            "booking_in_progress": previous_state.get("booking_in_progress", False),
            "selected_package_id": package_id if is_booking else previous_state.get("selected_package_id"),
            
            # INVOICE STATE
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
            
            # TRAVEL PACKAGES
            "travel_packages_html": result.get("travel_packages_html"),
            "travel_packages": result.get("travel_packages", []),
            
            # BOOKING STATE (preserve from result if available, else from previous_state)
            "passport_uploaded": result.get("passport_uploaded", previous_state.get("passport_uploaded", False)),
            "passport_data": result.get("passport_data", previous_state.get("passport_data", [])),
            "visa_uploaded": result.get("visa_uploaded", previous_state.get("visa_uploaded", False)),
            "visa_data": result.get("visa_data", previous_state.get("visa_data", [])),
            "booking_in_progress": result.get("booking_in_progress", previous_state.get("booking_in_progress", False)),
            "selected_package_id": result.get("selected_package_id", previous_state.get("selected_package_id")),
            
            # INVOICE STATE
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

            # Check if visa info was generated during the flow
            if result.get("visa_info_html"):
                print("✓ Returning visa_info_html from Amadeus flow")
                conversation_store.add_message(request.thread_id, "assistant", "Visa requirements provided")
                return result["visa_info_html"]

            if result.get("booking_html"):
                print("✓ Returning booking_html from Amadeus flow")
                booking_status = "Booking confirmed" if result.get("booking_confirmed") else "Booking in progress"
                conversation_store.add_message(request.thread_id, "assistant", booking_status)
                return result["booking_html"]

            if result.get("needs_followup", True):
                assistant_message = result.get("followup_question", "Could you provide more details about your flight?")
                conversation_store.add_message(request.thread_id, "assistant", assistant_message)
                html_content = question_to_html(assistant_message, extracted_info)
                return html_content

            if result.get("travel_packages_html"):
                print(f"✓ Returning {len(result['travel_packages_html'])} travel packages (HTML)")
                state_to_save["travel_search_completed"] = True
                state_to_save["travel_packages"] = result.get("travel_packages", [])  
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
        
        # 4. UNKNOWN tool_id
        else:
            print(f"⚠️ Unknown tool_id: {tool_id}")
            return """
            <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p class="text-yellow-700">Unknown request type. Please specify a valid tool_id.</p>
            </div>
            """

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
    
# Add this endpoint after your existing endpoints
# Add this endpoint after your existing endpoints in main.py
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

        # CRITICAL FIX: Retrieve existing state to preserve travel_packages
        current_state = conversation_store.get_state(thread_id) or {}
        
        logging.info(f"📦 Current state has {len(current_state.get('travel_packages', []))} packages")

        # Save state - PRESERVE ALL TRAVEL DATA
        state_to_save = {
            "passport_uploaded": True,
            "passport_data": passports_data,
            "passport_html": html_content,
            "passport_file_paths": saved_paths,
            # Preserve travel search data
            "travel_packages": current_state.get("travel_packages", []),
            "travel_packages_html": current_state.get("travel_packages_html"),
            "departure_date": current_state.get("departure_date"),
            "origin": current_state.get("origin"),
            "destination": current_state.get("destination"),
            "cabin_class": current_state.get("cabin_class"),
            "duration": current_state.get("duration"),
            # Preserve booking state
            "booking_in_progress": current_state.get("booking_in_progress", False),
            "selected_package_id": current_state.get("selected_package_id"),
            # Preserve visa data if exists
            "visa_uploaded": current_state.get("visa_uploaded", False),
            "visa_data": current_state.get("visa_data", []),
        }
        conversation_store.save_state(thread_id, state_to_save)
        
        logging.info(f"✅ Saved state with {len(state_to_save.get('travel_packages', []))} packages preserved")
        
        # If user is in booking flow, automatically trigger booking verification
        if current_state.get("booking_in_progress"):
            logger.info("📦 User in booking flow - will auto-verify on next message")
        
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


from Utils.visa_decoder import process_visa_file,generate_visa_html
from fastapi.responses import JSONResponse


# Add VISA_DIR to directory structure at the top of main.py
VISA_DIR = UPLOAD_DIR / "visas"

# Update the directory creation loop to include VISA_DIR
for directory in [DATA_DIR, UPLOAD_DIR, PDF_DIR, JSON_DIR, PASSPORT_DIR, VISA_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


@app.post("/api/visas/upload", response_class=HTMLResponse)
async def upload_visas(files: List[UploadFile], thread_id: str = Form(...)):
    """
    Handle multiple visa uploads (PDF, image, or Word doc) and return clean HTML for display.
    """
    try:
        if not thread_id:
            raise HTTPException(status_code=400, detail="thread_id is required")
        if not files:
            raise HTTPException(status_code=400, detail="No visa files uploaded")

        conversation_store.add_message(thread_id, "user", f"Uploaded {len(files)} visa file(s)")
        visas_data, saved_paths = [], []

        for file in files:
            try:
                extension = file.filename.lower().split('.')[-1]
                if extension not in ['pdf', 'jpg', 'jpeg', 'png', 'bmp', 'tiff', 'doc', 'docx']:
                    visas_data.append({
                        "filename": file.filename,
                        "error": f"Unsupported file format: {extension}"
                    })
                    continue

                filename = f"{uuid.uuid4()}_{file.filename}"
                temp_file_path = VISA_DIR / filename
                with open(temp_file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                logging.info(f"Saved visa file: {temp_file_path}")
                saved_paths.append(str(temp_file_path))

                visa_info = process_visa_file(str(temp_file_path))

                essential_fields = {
                    "filename": file.filename,
                    "saved_path": str(temp_file_path),
                    "visa_type": visa_info.get("visa_type"),
                    "visa_number": visa_info.get("visa_number"),
                    "country": visa_info.get("country"),
                    "full_name": visa_info.get("full_name"),
                    "nationality": visa_info.get("nationality"),
                    "passport_number": visa_info.get("passport_number"),
                    "date_of_birth": visa_info.get("date_of_birth"),
                    "date_of_issue": visa_info.get("date_of_issue"),
                    "date_of_expiry": visa_info.get("date_of_expiry"),
                    "place_of_birth": visa_info.get("place_of_birth"),
                    "place_of_issue": visa_info.get("place_of_issue"),
                    "profession": visa_info.get("profession"),
                    "uid_number": visa_info.get("uid_number"),
                    "host_name": visa_info.get("host_name"),
                    "host_address": visa_info.get("host_address"),
                    "validation_warnings": visa_info.get("validation_warnings", []),
                    "extraction_confidence": visa_info.get("extraction_confidence"),
                }

                if "error" in visa_info:
                    essential_fields["error"] = visa_info["error"]

                visas_data.append(essential_fields)

                if "error" not in visa_info:
                    logging.info(f"✅ Extracted visa info from {file.filename}")
                else:
                    logging.warning(f"⚠️ Failed to extract info from {file.filename}: {visa_info['error']}")

            except Exception as e:
                logging.error(f"Exception processing visa {file.filename}: {e}")
                traceback.print_exc()
                visas_data.append({
                    "filename": file.filename,
                    "error": f"Processing error: {str(e)}"
                })

        # CRITICAL FIX: Retrieve existing state to preserve travel_packages
        current_state = conversation_store.get_state(thread_id) or {}
        
        logging.info(f"📦 Current state has {len(current_state.get('travel_packages', []))} packages")

        # Save with proper flags - PRESERVE travel_packages
        state_to_save = {
            "visa_uploaded": True,
            "visa_data": visas_data,
            "visa_file_paths": saved_paths,
            # Preserve travel search data
            "travel_packages": current_state.get("travel_packages", []),
            "travel_packages_html": current_state.get("travel_packages_html"),
            "departure_date": current_state.get("departure_date"),
            "origin": current_state.get("origin"),
            "destination": current_state.get("destination"),
            "cabin_class": current_state.get("cabin_class"),
            "duration": current_state.get("duration"),
            # Preserve booking state
            "booking_in_progress": current_state.get("booking_in_progress", False),
            "selected_package_id": current_state.get("selected_package_id"),
            # Preserve passport data if exists
            "passport_uploaded": current_state.get("passport_uploaded", False),
            "passport_data": current_state.get("passport_data", []),
        }
        conversation_store.save_state(thread_id, state_to_save)
        
        logging.info(f"✅ Saved state with {len(state_to_save.get('travel_packages', []))} packages preserved")
        
        # If user is in booking flow, automatically trigger booking verification
        if current_state.get("booking_in_progress"):
            logger.info("📦 User in booking flow - will auto-verify on next message")
        
        # Generate HTML summary
        html_summary = generate_visa_html(visas_data)

        # Return only the clean HTML
        return HTMLResponse(content=html_summary, status_code=200)

    except Exception as e:
        logging.error(f"Unexpected error in /api/visas/upload: {e}")
        traceback.print_exc()
        return HTMLResponse(content=f"<div>An unexpected error occurred: {str(e)}</div>", status_code=500)