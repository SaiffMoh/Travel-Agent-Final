from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from .. import schemas, crud
from ..database import get_db
from ..deps import get_current_active_user
from fastapi.responses import JSONResponse
from Models.ChatRequest import ChatRequest
from Models.ChatResponse import ChatResponse
from Models.ExtractedInfo import ExtractedInfo
from Utils.routing import detect_visa_inquiry, detect_booking_intent
from Nodes.visa_rag_node import visa_rag_node
from Nodes.web_search_node import web_search_node
from Nodes.greeting_conversation_node import greeting_conversation_node
from Utils.question_to_html import question_to_html
from graph import create_travel_graph
import logging, traceback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/travel/chat", tags=["chat"])
graph = create_travel_graph().compile()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    try:
        thread_id = request.thread_id
        user_message = request.user_msg.strip()
        tool_id = request.tool_id
        if not thread_id:
            raise HTTPException(status_code=400, detail="thread_id is required")
        if not user_message:
            raise HTTPException(status_code=400, detail="user_msg cannot be empty")
        # Ensure thread exists in DB
        thread = await crud.get_chat_thread(db, thread_id)
        if thread is None:
            thread = await crud.create_chat_thread(db, thread_id, user_id=current_user.id)
        elif thread.user_id is not None and thread.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="You do not have access to this thread.")
        previous_state = await crud.get_conversation_state(db, thread_id) or {}
        temp_state = {
            "thread_id": thread_id,
            "current_message": user_message,
            "user_message": user_message,
            "destination": previous_state.get("destination")
        }
        is_visa_inquiry, detected_country = detect_visa_inquiry(temp_state)
        if is_visa_inquiry:
            await crud.create_chat_message(db, thread_id, user_message, "")
            state = {
                "thread_id": thread_id,
                "user_message": user_message,
                "current_message": user_message,
                "detected_visa_country": detected_country,
                "destination": temp_state.get("destination"),
                "visa_info_html": None
            }
            result = visa_rag_node(state)
            await crud.create_chat_message(db, thread_id, "", "Visa requirements provided")
            await crud.save_conversation_state(db, thread_id, {
                "visa_info_html": result.get("visa_info_html"),
                "detected_visa_country": detected_country
            })
            return ChatResponse(html_content=result["visa_info_html"])
        if tool_id == "web_search":
            await crud.create_chat_message(db, thread_id, user_message, "")
            state = {
                "thread_id": thread_id,
                "user_message": user_message,
                "current_message": user_message,
                "web_search_result": None,
                "web_search_html": None,
                "web_search_error": None
            }
            result = web_search_node(state)
            if result.get("web_search_error"):
                await crud.create_chat_message(db, thread_id, "", "Web search failed")
                return ChatResponse(html_content=result["web_search_html"])
            await crud.create_chat_message(db, thread_id, "", "Web search results provided")
            await crud.save_conversation_state(db, thread_id, {
                "web_search_result": result.get("web_search_result"),
                "web_search_html": result.get("web_search_html")
            })
            return ChatResponse(html_content=result["web_search_html"])
        elif tool_id is None or tool_id == "greeting":
            conversation_history = await crud.get_messages_for_thread(db, thread_id)
            await crud.create_chat_message(db, thread_id, user_message, "")
            state = {
                "thread_id": thread_id,
                "user_message": user_message,
                "current_message": user_message,
                "conversation": conversation_history,
                "greeting_response": None,
                "greeting_html": None,
                "greeting_error": None
            }
            result = greeting_conversation_node(state)
            if result.get("greeting_error"):
                await crud.create_chat_message(db, thread_id, "", "Conversation error")
                return ChatResponse(html_content=result["greeting_html"])
            assistant_message = result.get("greeting_response", "I'm here to help!")
            await crud.create_chat_message(db, thread_id, "", assistant_message)
            await crud.save_conversation_state(db, thread_id, {
                "greeting_response": result.get("greeting_response"),
                "greeting_html": result.get("greeting_html")
            })
            return ChatResponse(html_content=result["greeting_html"])
        elif tool_id == "amadeus":
            conversation_history = await crud.get_messages_for_thread(db, thread_id)
            await crud.create_chat_message(db, thread_id, user_message, "")
            updated_conversation = await crud.get_messages_for_thread(db, thread_id)
            is_booking, package_id = detect_booking_intent({
                "current_message": user_message,
                "user_message": user_message,
                "booking_in_progress": previous_state.get("booking_in_progress", False)
            })
            # Always include travel_packages and travel_packages_html from previous_state
            travel_packages = previous_state.get("travel_packages", [])
            travel_packages_html = previous_state.get("travel_packages_html")
            state = {
                "thread_id": thread_id,
                "user_id": current_user.id,
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
                "travel_packages": travel_packages,
                "travel_packages_html": travel_packages_html,
                "passport_uploaded": previous_state.get("passport_uploaded", False),
                "passport_data": previous_state.get("passport_data", []),
                "visa_uploaded": previous_state.get("visa_uploaded", False),
                "visa_data": previous_state.get("visa_data", []),
                "booking_in_progress": previous_state.get("booking_in_progress", False),
                "selected_package_id": package_id if is_booking else previous_state.get("selected_package_id"),
                "invoice_uploaded": previous_state.get("invoice_uploaded", False),
                "invoice_pdf_path": previous_state.get("invoice_pdf_path"),
                "extracted_invoice_data": previous_state.get("extracted_invoice_data"),
                "invoice_html": previous_state.get("invoice_html")
            }
            travel_fields = ["departure_date", "origin", "destination", "cabin_class", "duration"]
            for field in travel_fields:
                if field in previous_state:
                    state[field] = previous_state[field]
            if graph is None:
                raise HTTPException(status_code=500, detail="Graph compilation failed")
            result = await graph.ainvoke(state)
            # Always persist travel_packages and travel_packages_html after search
            travel_packages = result.get("travel_packages")
            travel_packages_html = result.get("travel_packages_html")
            # Preserve from previous_state if not present in result
            if travel_packages is None:
                travel_packages = previous_state.get("travel_packages", [])
            if travel_packages_html is None:
                travel_packages_html = previous_state.get("travel_packages_html")
            logger.info(f"Saving to DB: travel_packages count: {len(travel_packages)}")
            logger.info(f"Saving to DB: travel_packages_html type: {type(travel_packages_html)}")
            await crud.save_conversation_state(db, thread_id, {
                "departure_date": result.get("departure_date"),
                "origin": result.get("origin"),
                "destination": result.get("destination"),
                "cabin_class": result.get("cabin_class"),
                "duration": result.get("duration"),
                "followup_count": result.get("followup_count", 0),
                "request_type": result.get("request_type", "flights"),
                "travel_search_completed": result.get("travel_search_completed", False),
                "travel_packages_html": travel_packages_html,
                "travel_packages": travel_packages,
                "passport_uploaded": result.get("passport_uploaded", previous_state.get("passport_uploaded", False)),
                "passport_data": result.get("passport_data", previous_state.get("passport_data", [])),
                "visa_uploaded": result.get("visa_uploaded", previous_state.get("visa_uploaded", False)),
                "visa_data": result.get("visa_data", previous_state.get("visa_data", [])),
                "booking_in_progress": result.get("booking_in_progress", previous_state.get("booking_in_progress", False)),
                "selected_package_id": result.get("selected_package_id", previous_state.get("selected_package_id")),
                "invoice_uploaded": result.get("invoice_uploaded", False),
                "invoice_pdf_path": result.get("invoice_pdf_path"),
                "extracted_invoice_data": result.get("extracted_invoice_data"),
                "invoice_html": result.get("invoice_html")
            })
            assistant_message = result.get("summary", "Here are your flight options:")
            await crud.create_chat_message(db, thread_id, "", assistant_message)
            if result.get("visa_info_html"):
                await crud.create_chat_message(db, thread_id, "", "Visa requirements provided")
                return ChatResponse(html_content=result["visa_info_html"])
            if result.get("booking_html"):
                booking_status = "Booking confirmed" if result.get("booking_confirmed") else "Booking in progress"
                await crud.create_chat_message(db, thread_id, "", booking_status)
                return ChatResponse(html_content=result["booking_html"])
            if result.get("needs_followup", True):
                assistant_message = result.get("followup_question", "Could you provide more details about your flight?")
                await crud.create_chat_message(db, thread_id, "", assistant_message)
                # Always pass an ExtractedInfo instance, never None
                extracted_info = ExtractedInfo(
                    departure_date=result.get("departure_date"),
                    origin=result.get("origin"),
                    destination=result.get("destination"),
                    cabin_class=result.get("cabin_class"),
                    trip_type=result.get("trip_type"),
                    duration=result.get("duration")
                )
                html_content = question_to_html(assistant_message, extracted_info)
                return ChatResponse(html_content=html_content)
            if result.get("travel_packages_html"):
                await crud.create_chat_message(db, thread_id, "", "Here are your travel packages:")
                travel_packages_html = result["travel_packages_html"]
                if isinstance(travel_packages_html, list):
                    travel_packages_html = "".join(travel_packages_html)
                return ChatResponse(html_content=travel_packages_html)
            return ChatResponse(html_content=assistant_message)
        else:
            return ChatResponse(html_content="""
            <div class='p-4 bg-yellow-50 border border-yellow-200 rounded-lg'>
                <p class='text-yellow-700'>Unknown request type. Please specify a valid tool_id.</p>
            </div>
            """)
    except HTTPException as he:
        logger.error(f"HTTPException: {he.detail}")
        traceback.print_exc()
        raise
    except Exception as e:
        logger.error(f"UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error while processing request")
