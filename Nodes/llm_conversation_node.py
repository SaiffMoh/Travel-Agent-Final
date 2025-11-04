import json
import os
import re
from Models.TravelSearchState import TravelSearchState
from langchain_core.messages import HumanMessage
from Utils.watson_config import llm
from Prompts.llm_conversation import build_input_extraction_prompt
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def llm_conversation_node(state: TravelSearchState) -> TravelSearchState:
    """Enhanced LLM-driven conversational node that intelligently handles all user input parsing and manages seamless flow transitions."""
    try:
        if not os.getenv("WATSON_APIKEY") or not os.getenv("PROJECT_ID"):
            logger.error("Missing WATSON_APIKEY or PROJECT_ID in .env")
            state["followup_question"] = "I need a Watsonx API key and project ID to help you with flight bookings."
            state["needs_followup"] = True
            state["current_node"] = "llm_conversation"
            return state

        llm_prompt = build_input_extraction_prompt(state)
        logger.info("llm_conversation_node: using JSON-mode LLM")
        
        # Format prompt for Watsonx
        prompt = f"<|SYSTEM|>{llm_prompt}<|USER|>Return the response in strict JSON format, with no prose, no backticks, no markdown, and no extra text. Only the JSON object matching the schema specified in the system prompt.<|END|>"
        logger.info(f"Watsonx prompt: {prompt[:500]}...")

        # Invoke Watsonx LLM
        response = llm.generate(prompt=prompt)
        reply = response["results"][0]["generated_text"].strip()
        logger.info(f"Watsonx LLM raw response: {reply}")
        cleaned_reply = re.sub(r"^```(?:json)?|```$", "", reply, flags=re.MULTILINE).strip()

        try:
            llm_result = json.loads(cleaned_reply)
            logger.info(f"LLM result: {llm_result}")
            
            # Pass the is_new_search flag to the state for the router to handle
            state["is_new_search"] = llm_result.get("is_new_search", False)
            
            # Update state with extracted information
            if llm_result.get("departure_date"):
                state["departure_date"] = llm_result["departure_date"]
            if llm_result.get("origin"):
                state["origin"] = llm_result["origin"]
            if llm_result.get("destination"):
                state["destination"] = llm_result["destination"]
            if llm_result.get("cabin_class"):
                state["cabin_class"] = llm_result["cabin_class"]
            if llm_result.get("duration") is not None:
                state["duration"] = llm_result["duration"]
            
            # NEW: Extract request_type and trip_type
            if llm_result.get("request_type"):
                state["request_type"] = llm_result["request_type"]
            else:
                # Default to packages if not specified
                state["request_type"] = state.get("request_type", "packages")
            
            if llm_result.get("trip_type"):
                state["trip_type"] = llm_result["trip_type"]
            else:
                # Default to round_trip if not specified
                state["trip_type"] = state.get("trip_type", "round_trip")

            # Update control flags
            state["followup_question"] = llm_result.get("followup_question")
            state["needs_followup"] = llm_result.get("needs_followup", True)
            state["info_complete"] = llm_result.get("info_complete", False)

            # Log extracted information
            logger.info(f"Updated state - Origin: {state.get('origin')}, Destination: {state.get('destination')}, Date: {state.get('departure_date')}")
            logger.info(f"Request type: {state.get('request_type')}, Trip type: {state.get('trip_type')}")
            logger.info(f"Info complete: {state.get('info_complete')}, Needs followup: {state.get('needs_followup')}")

        except json.JSONDecodeError as je:
            logger.error(f"LLM response parsing error: {je}, raw response: {reply}")
            state["followup_question"] = "I had trouble understanding. Could you please tell me your departure city, destination, and preferred travel date?"
            state["needs_followup"] = True
            state["info_complete"] = False

    except Exception as e:
        logger.error(f"Error in LLM conversation node: {e}")
        state["followup_question"] = "I'm having technical difficulties. Please try again with your travel details."
        state["needs_followup"] = True
        state["info_complete"] = False

    state["current_node"] = "llm_conversation"
    return state