# Enhanced llm_conversation_node.py

import json
import os
from Models.TravelSearchState import TravelSearchState
from langchain.schema import HumanMessage
from Utils.getLLM import get_llm_json
from Prompts.llm_conversation import build_input_extraction_prompt

def llm_conversation_node(state: TravelSearchState) -> TravelSearchState:
    """Enhanced LLM-driven conversational node that intelligently handles all user input parsing and manages seamless flow transitions."""

    try:
        if not os.getenv("OPENAI_API_KEY"):
            state["followup_question"] = "I need an OpenAI API key to help you with flight bookings."
            state["needs_followup"] = True
            state["current_node"] = "llm_conversation"
            return state

        llm_prompt = build_input_extraction_prompt(state)
        print("llm_conversation_node: using JSON-mode LLM (response_format=json_object)")
        response = get_llm_json().invoke([HumanMessage(content=llm_prompt)])
        print(f"llm_conversation_node: got response length={len(response.content) if hasattr(response, 'content') else 'n/a'}")

        try:
            llm_result = json.loads(response.content)
            print(f"LLM result: {llm_result}")
            
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

            # Update control flags
            state["followup_question"] = llm_result.get("followup_question")
            state["needs_followup"] = llm_result.get("needs_followup", True)
            state["info_complete"] = llm_result.get("info_complete", False)

            # If LLM believes it's complete, set request type
            if llm_result.get("info_complete"):
                state["request_type"] = state.get("request_type") or "flights"
                
            print(f"Updated state - Origin: {state.get('origin')}, Destination: {state.get('destination')}, Date: {state.get('departure_date')}")
            print(f"Info complete: {state.get('info_complete')}, Needs followup: {state.get('needs_followup')}")

        except json.JSONDecodeError:
            print(f"LLM response parsing error. Raw response: {response.content}")
            state["followup_question"] = "I had trouble understanding. Could you please tell me your departure city, destination, and preferred travel date?"
            state["needs_followup"] = True
            state["info_complete"] = False

    except Exception as e:
        print(f"Error in LLM conversation node: {e}")
        state["followup_question"] = "I'm having technical difficulties. Please try again with your flight details."
        state["needs_followup"] = True
        state["info_complete"] = False

    state["current_node"] = "llm_conversation"
    return state