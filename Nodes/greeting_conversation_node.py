# Nodes/greeting_conversation_node.py
"""
Greeting and General Travel Conversation Node
Handles casual conversations, greetings, and general travel advice
Uses Watson LLM for natural, helpful responses
"""

import logging
from typing import Dict, Any
from Utils.watson_config import llm_generic
import html

logger = logging.getLogger(__name__)

# System prompt for greeting/casual conversation
GREETING_SYSTEM_PROMPT = """You are a friendly and helpful AI travel assistant for a travel booking platform. Your role is to:

1. **Greet users warmly** and welcome them to the travel booking service
2. **Explain capabilities** when asked what you can do:
   - Search for flights and hotels
   - Create complete travel packages
   - Provide visa requirement information
   - Answer general travel questions
   - Process travel invoices
   - Search the web for travel-related information
   
3. **Provide general travel advice** such as:
   - Best times to visit destinations
   - Travel tips and recommendations
   - General information about cities and countries
   - Cultural insights and travel etiquette
   
4. **Engage in friendly conversation** about travel topics

5. **Guide users** to use specific features:
   - "To search for flights and hotels, just tell me your travel plans!"
   - "Need visa information? Ask me about visa requirements for your destination."
   - "Want to search the web? I can help with that too!"

**Important Guidelines:**
- Keep responses concise and friendly (2-4 sentences)
- If the user asks about specific flights/hotels, suggest they provide their travel details
- Don't make up specific flight prices or hotel information
- Be encouraging and helpful
- Use a warm, conversational tone

**Example Interactions:**
User: "Hello"
Assistant: "Hello! 👋 Welcome to our AI travel assistant. I can help you search for flights and hotels, check visa requirements, and answer your travel questions. What would you like to explore today?"

User: "What can you do?"
Assistant: "I'm here to make your travel planning easy! I can search for flights and hotel packages, provide visa information, answer general travel questions, and even search the web for you. Just tell me where you'd like to go, and I'll help you find the perfect options!"

User: "What's the best time to visit Dubai?"
Assistant: "Dubai is best visited from November to March when temperatures are pleasant (20-30°C). Avoid summer months (June-August) as it can be extremely hot. The Dubai Shopping Festival in January is also a great time to visit for deals and events!"

Now respond to the user's message naturally and helpfully."""


def greeting_conversation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle greeting and general travel conversations using Watson LLM.
    
    Args:
        state: Dictionary containing:
            - user_message: The user's message
            - thread_id: Conversation thread identifier
            - conversation: Optional conversation history
            
    Returns:
        Updated state with:
            - greeting_response: Text response from LLM
            - greeting_html: HTML-formatted response for display
            - greeting_error: Error message if something fails
    """
    try:
        user_message = state.get("user_message", "").strip()
        
        if not user_message:
            logger.error("No user message provided for greeting conversation")
            state["greeting_error"] = "No message provided"
            state["greeting_html"] = generate_error_html("Please provide a message.")
            return state
        
        logger.info(f"Processing greeting/casual conversation: {user_message}")
        
        # Get conversation history if available for context
        conversation_history = state.get("conversation", [])
        
        # Build context from recent messages (last 3 exchanges)
        context = ""
        if conversation_history and len(conversation_history) > 0:
            recent_messages = conversation_history[-6:]  # Last 3 user + 3 assistant
            for msg in recent_messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                context += f"{role.capitalize()}: {content}\n"
        
        # Construct the full prompt
        full_prompt = f"{GREETING_SYSTEM_PROMPT}\n\n"
        if context:
            full_prompt += f"Previous conversation context:\n{context}\n\n"
        full_prompt += f"User: {user_message}\n\nAssistant:"
        
        logger.info("Sending prompt to Watson LLM (generic model)")
        
        # Generate response using Watson LLM
        response = llm_generic.generate(
            prompt=full_prompt,
            params={
                'temperature': 0.7,  # Slightly higher for more natural conversation
                'max_tokens': 500    # Limit response length
            }
        )
        
        # Extract response text
        if response and 'results' in response and len(response['results']) > 0:
            assistant_response = response['results'][0]['generated_text'].strip()
            
            logger.info(f"Generated response length: {len(assistant_response)}")
            
            # Store results in state
            state["greeting_response"] = assistant_response
            state["greeting_html"] = generate_greeting_html(user_message, assistant_response)
            state["greeting_error"] = None
            
            return state
        else:
            logger.error("Empty response from Watson LLM")
            state["greeting_error"] = "No response from LLM"
            state["greeting_html"] = generate_error_html("Unable to generate response. Please try again.")
            return state
            
    except Exception as e:
        logger.error(f"Error in greeting conversation node: {str(e)}")
        state["greeting_error"] = str(e)
        state["greeting_html"] = generate_error_html(f"An error occurred: {str(e)}")
        return state


def generate_greeting_html(user_query: str, assistant_response: str) -> str:
    """
    Generate simple HTML for greeting/conversation response.
    """
    import html
    escaped_response = html.escape(assistant_response)
    formatted_response = escaped_response.replace('\n', '<br>')
    return f"""
    <div class="greeting-text">
        {formatted_response}
    </div>
    """



def generate_error_html(error_message: str) -> str:
    """
    Generate HTML for displaying error messages.
    
    Args:
        error_message: The error message to display
        
    Returns:
        HTML-formatted error string
    """
    escaped_error = html.escape(error_message)
    
    html_content = f"""
    <div class="greeting-error p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
        <div class="flex items-start gap-3">
            <svg class="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            <div>
                <h3 class="text-lg font-semibold text-red-700 dark:text-red-400 mb-1">Conversation Error</h3>
                <p class="text-red-600 dark:text-red-300">{escaped_error}</p>
                <p class="text-sm text-gray-600 dark:text-gray-400 mt-2">Please try again or rephrase your message.</p>
            </div>
        </div>
    </div>
    """
    
    return html_content