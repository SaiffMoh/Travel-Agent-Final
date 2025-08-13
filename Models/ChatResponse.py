from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, TypedDict
from datetime import datetime
class ChatResponse(BaseModel):
    html_content: str = Field(..., description="Full HTML content for frontend display")