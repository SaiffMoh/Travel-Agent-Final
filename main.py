from fastapi import FastAPI, HTTPException
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

# Updated chat endpoint section in main.py

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

        # Load conversation and previous state
        conversation_history = conversation_store.get_conversation(request.thread_id)
        print(f"✓ Got conversation history: {len(conversation_history)} messages")
        
        conversation_store.add_message(request.thread_id, "user", user_message)
        updated_conversation = conversation_store.get_conversation(request.thread_id)
        print(f"✓ Updated conversation: {len(updated_conversation)} messages")

        # Load previous state if it exists
        previous_state = conversation_store.get_state(request.thread_id) or {}
        
        # Build initial state - don't automatically carry over travel_search_completed
        # Let the smart router decide based on user intent
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
            # Only carry over travel_search_completed if it's relevant to current intent
            "travel_search_completed": previous_state.get("travel_search_completed", False),
            "visa_info_html": None
        }
        
        # Conditionally carry over previous travel data
        # The smart router will reset these if a new search is detected
        travel_fields = ["departure_date", "origin", "destination", "cabin_class", "duration", "travel_packages_html"]
        for field in travel_fields:
            if field in previous_state:
                state[field] = previous_state[field]

        if graph is None:
            print("ERROR: Graph was not compiled at startup")
            raise HTTPException(status_code=500, detail="Graph compilation failed")

        # Run LangGraph workflow with enhanced routing
        result = graph.invoke(state)
        
        print("✓ LangGraph execution completed")
        
        # Enhanced debugging
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
            print(f"Travel search completed: {result.get('travel_search_completed', False)}")
        except Exception as _:
            print("(debug) unable to print result keys")

        # Save state for persistence - include all relevant fields
        state_to_save = {
            "departure_date": result.get("departure_date"),
            "origin": result.get("origin"),
            "destination": result.get("destination"),
            "cabin_class": result.get("cabin_class"),
            "duration": result.get("duration"),
            "followup_count": result.get("followup_count", 0),
            "request_type": result.get("request_type", "flights"),
            "travel_search_completed": result.get("travel_search_completed", False),
            "travel_packages_html": result.get("travel_packages_html")
        }
        conversation_store.save_state(request.thread_id, state_to_save)

        # Build extracted info for response
        extracted_info = ExtractedInfo(
            departure_date=result.get("departure_date"),
            origin=result.get("origin"),
            destination=result.get("destination"),
            cabin_class=result.get("cabin_class"),
            trip_type=result.get("trip_type"),
            duration=result.get("duration")
        )

        # Check for visa info
        if result.get("visa_info_html"):
            print("✓ Returning visa_info_html")
            conversation_store.add_message(request.thread_id, "assistant", "Visa requirements provided")
            return result["visa_info_html"]

        # If still collecting information, return follow-up question
        if result.get("needs_followup", True):
            assistant_message = result.get("followup_question", "Could you provide more details about your flight?")
            conversation_store.add_message(request.thread_id, "assistant", assistant_message)
            html_content = question_to_html(assistant_message, extracted_info)
            return html_content

        # If we have travel packages HTML, return it and mark search complete
        if result.get("travel_packages_html"):
            print(f"✓ Returning {len(result['travel_packages_html'])} travel packages (HTML)")
            # Update the saved state to mark search as completed
            state_to_save["travel_search_completed"] = True
            conversation_store.save_state(request.thread_id, state_to_save)
            
            assistant_message = "Here are your travel packages:"
            conversation_store.add_message(request.thread_id, "assistant", assistant_message)
            return result["travel_packages_html"]

        # Build flight results if search completed (fallback)
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