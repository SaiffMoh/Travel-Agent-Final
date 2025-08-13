from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import os

load_dotenv()
_llm = None

def get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("LLM unavailable: OPENAI_API_KEY not set")
        _llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.1,
            api_key=api_key
        )
    return _llm