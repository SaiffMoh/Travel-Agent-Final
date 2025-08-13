from datetime import datetime
import json
import os
from langchain.schema import HumanMessage
from ..Models import FlightSearchState
from ..Utils import get_llm, _debug_print  # adjust imports as needed

def llm_conversation_node(state: FlightSearchState) -> FlightSearchState:
    """LLM-driven conversational node that intelligently handles all user input parsing and follow-up questions."""
    try:
        (state.setdefault("node_trace", [])).append("llm_conversation")
    except Exception:
        pass

    conversation_text = "".join(f"{m['role']}: {m['content']}\n" for m in state.get("conversation", []))
    user_text = state.get("current_message", "")

    current_date = datetime.now()
    current_date_str = current_date.strftime("%Y-%m-%d")
    current_month = current_date.month
    current_day = current_date.day
    current_year = current_date.year

    try:
        if not os.getenv("OPENAI_API_KEY"):
            state["followup_question"] = "I need an OpenAI API key to help you with flight bookings."
            state["needs_followup"] = True
            state["current_node"] = "llm_conversation"
            return state

        llm_prompt = f"""..."""  # Keep your full original prompt here
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

            _debug_print("LLM extraction result", llm_result)
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
