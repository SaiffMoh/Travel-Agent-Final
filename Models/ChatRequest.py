from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, TypedDict
from datetime import datetime
class ChatRequest(BaseModel):
    thread_id: str = Field(..., description="Unique identifier for the conversation thread")
    user_msg: str = Field(..., description="The user's message")