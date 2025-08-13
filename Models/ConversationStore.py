from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, TypedDict
from datetime import datetime

class ConversationStore:
    def __init__(self):
        self._conversations: Dict[str, List[Dict[str, Any]]] = {}
    
    def get_conversation(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get conversation history for a thread"""
        return self._conversations.get(thread_id, [])
    
    def add_message(self, thread_id: str, role: str, content: str) -> None:
        """Add a message to conversation history"""
        if thread_id not in self._conversations:
            self._conversations[thread_id] = [
                {
                    "role": "system", 
                    "content": (
                        "You are a helpful AI travel assistant specializing in flight bookings. "
                        "Your goal is to help users find the best flights by gathering their preferences "
                        "in a natural, conversational way. You can understand flexible date formats, "
                        "casual location names, and abbreviated terms. Always be friendly and efficient."
                    ),
                    "timestamp": datetime.now().isoformat()
                }
            ]
        
        self._conversations[thread_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def clear_conversation(self, thread_id: str) -> None:
        """Clear conversation history for a thread"""
        if thread_id in self._conversations:
            del self._conversations[thread_id]
    
    def get_all_threads(self) -> List[str]:
        """Get all active thread IDs"""
        return list(self._conversations.keys())

# Global conversation store instance
conversation_store = ConversationStore()