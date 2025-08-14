from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import os

load_dotenv()

_llm_json = None
_llm_text = None


def get_llm_json() -> ChatOpenAI:
	"""Returns the JSON-mode LLM used for structured extraction."""
	global _llm_json
	if _llm_json is None:
		api_key = os.getenv("OPENAI_API_KEY")
		if not api_key:
			raise RuntimeError("LLM unavailable: OPENAI_API_KEY not set")
		_llm_json = ChatOpenAI(
			model="gpt-4o-mini",
			temperature=0.1,
			api_key=api_key,
			response_format={"type": "json_object"},
		)
	return _llm_json


def get_text_llm() -> ChatOpenAI:
	"""Returns a text-mode LLM for natural language responses (no JSON forcing)."""
	global _llm_text
	if _llm_text is None:
		api_key = os.getenv("OPENAI_API_KEY")
		if not api_key:
			raise RuntimeError("LLM unavailable: OPENAI_API_KEY not set")
		_llm_text = ChatOpenAI(
			model="gpt-4o-mini",
			temperature=0.2,
			api_key=api_key,
		)
	return _llm_text


def get_llm() -> ChatOpenAI:
	"""Backward-compatible alias to the JSON-mode LLM."""
	return get_llm_json()
