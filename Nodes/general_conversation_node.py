# Nodes/general_conversation_node.py

from Models.TravelSearchState import TravelSearchState

def general_conversation_node(state: TravelSearchState) -> TravelSearchState:
    """Handle general conversation that's not travel or visa related"""
    user_message = state.get("current_message") or state.get("user_message", "")
    
    # Simple conversational responses for non-travel queries
    responses = {
        "hello": "Hello! I'm here to help you with flight bookings and travel information. What can I assist you with today?",
        "hi": "Hi there! How can I help you with your travel plans?",
        "thank": "You're welcome! Is there anything else I can help you with for your travels?",
        "help": "I can help you search for flights, hotels, travel packages, and provide visa information. What would you like to know?",
        "how are you": "I'm doing great and ready to help with your travel needs! What can I assist you with?",
        "what can you do": "I can help you find flights, search for hotels, create travel packages, and provide visa requirement information for different countries. Just tell me where you'd like to go!"
    }
    
    message_lower = user_message.lower()
    response = None
    
    # Find matching response
    for keyword, reply in responses.items():
        if keyword in message_lower:
            response = reply
            break
    
    # Default response if no specific match
    if not response:
        response = "I'm here to help with travel-related queries. You can ask me about flights, hotels, travel packages, or visa requirements. What would you like to know?"
    
    state["followup_question"] = response
    state["needs_followup"] = True
    state["info_complete"] = False
    
    return state