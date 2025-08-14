import json
import os
from Models.TravelSearchState import TravelSearchState
from langchain.schema import HumanMessage
from Utils.getLLM import get_llm_json
from Prompts.llm_conversation import build_input_extraction_prompt

def llm_conversation_node(state: TravelSearchState) -> TravelSearchState:
    """LLM-driven conversational node that intelligently handles all user input parsing and follow-up questions."""

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

            # Capture follow-up suggestion but don't force flags here; analyze node decides
            state["followup_question"] = llm_result.get("followup_question")

            # If LLM believes it's complete, keep a hint
            if llm_result.get("info_complete"):
                state["request_type"] = state.get("request_type") or "flights"

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
