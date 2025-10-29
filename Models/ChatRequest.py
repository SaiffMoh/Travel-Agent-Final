# Models/ChatRequest.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, TypedDict
from datetime import datetime

class ChatRequest(BaseModel):
    thread_id: str = Field(..., description="Unique identifier for the conversation thread")
    user_msg: str = Field(..., description="The user's message")
    tool_id: Optional[str] = Field(None, description="Optional tool identifier for routing (e.g., 'web_search')")
    
    class Config:
        json_schema_extra = {
            "example": {
                "thread_id": "user_123",
                "user_msg": "I want to fly from Cairo to Dubai",
                "tool_id": None  # or "web_search" for web search functionality
            }
        }