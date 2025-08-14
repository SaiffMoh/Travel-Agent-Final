import json
import os
from Models.TravelSearchState import TravelSearchState
from langchain.schema import HumanMessage
from Utils.getLLM import get_llm
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
        response = get_llm().invoke([HumanMessage(content=llm_prompt)])

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
            if llm_result.get("duration"):
                state["duration"] = llm_result["duration"]

            state["followup_question"] = llm_result.get("followup_question")
            state["needs_followup"] = llm_result.get("needs_followup", True)
            state["info_complete"] = llm_result.get("info_complete", False)

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
