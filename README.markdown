# Travel Agent API

Welcome to the **Travel Agent API**, an AI-powered flight and hotel search assistant built with FastAPI and LangGraph. This application allows users to interact with a conversational AI to search for flight and hotel packages, leveraging the Amadeus API for travel data, IBM watsonx.ai as the primary LLM, and OpenAI embeddings for the visa RAG component.

## Overview

The Travel Agent API is designed to:

- Process user queries via a chat interface.
- Extract travel preferences (e.g., departure date, origin, destination, cabin class, duration).
- Fetch flight and hotel offers using the Amadeus API.
- Create travel packages combining flights and hotels.
- Generate HTML summaries of available packages.

The application uses a stateful graph-based workflow managed by LangGraph, with nodes handling specific tasks like conversation analysis, API calls, and package creation.

## Features

- **Conversational Interface**: Users can interact via a thread-based chat system.
- **Flight Search**: Retrieves flight offers for three consecutive days using the Amadeus API.
- **Hotel Search**: Fetches hotel offers based on flight-derived check-in and check-out dates.
- **Package Creation**: Combines flight and hotel data into travel packages.
- **HTML Output**: Generates formatted HTML for package summaries.
- **API Health Check**: Monitors API key availability and server status.
- **Conversation Reset**: Allows resetting conversation history by thread ID.
// ... existing code ...
// Additional key functionality
- **Visa Requirements (RAG)**: Answers visa questions using a FAISS vector store built with OpenAI embeddings and generates responses with IBM watsonx.ai.

## Directory Structure

```
Travel-Agent-Final/
├── Nodes/                       # Core workflow nodes (start here for core functionalities)
│   ├── analyze_conversation_node.py
│   ├── create_packages.py
│   ├── flight_inquiry_node.py
│   ├── format_body_node.py
│   ├── general_conversation_node.py
│   ├── get_access_token_node.py
│   ├── get_city_IDs_node.py
│   ├── get_flight_offers_node.py
│   ├── get_hotel_offers_node.py
│   ├── invoice_extraction_node.py
│   ├── llm_conversation_node.py
│   ├── normalize_info_node.py
│   ├── parse_company_hotels_node.py
│   ├── summarize_packages.py
│   ├── toHTML.py
│   └── visa_rag_node.py
├── Models/
│   ├── TravelSearchState.py
│   ├── ChatRequest.py
│   ├── ExtractedInfo.py
│   ├── FlightResult.py
│   ├── InvoiceModels.py
│   ├── Message.py
│   └── ConversationStore.py
├── Utils/
│   ├── build_vector_store.py
│   ├── decisions.py
│   ├── getLLM.py
│   ├── intent_detection.py
│   ├── invoice_to_html.py
│   ├── question_to_html.py
│   ├── routing.py
│   └── watson_config.py
├── Prompts/
│   ├── airport_prompt.py
│   ├── cabin_prompt.py
│   ├── greeterPrompt.py
│   ├── llm_conversation.py
│   └── summary_prompt.py
├── data/
│   └── visa_vector_store/       # FAISS store built with OpenAI embeddings
├── main.py
├── graph.py
├── .env
├── requirments.txt              # Note: dependency file name
└── README.markdown
```

## Prerequisites

- **Python 3.9+**
- **Amadeus API Credentials**: `AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET`
- **IBM watsonx.ai Credentials**: `WATSON_APIKEY`, `PROJECT_ID`
- **OpenAI API Key (for embeddings)**: `OPENAI_API_KEY`

## Setup

1. **Clone the Repository**

   ```bash
   git clone https://github.com/SaiffMoh/Travel-Agent-Final.git
   cd Travel-Agent-Final
   ```

2. **Install Dependencies**Create a virtual environment and install required packages:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirments.txt
   ```

3. **Configure Environment Variables**Create a `.env` file in the project root with the following:

   ```
   # IBM watsonx.ai (primary LLM)
   WATSON_APIKEY=your_watson_api_key
   PROJECT_ID=your_watson_project_id

   # OpenAI (embeddings for visa RAG)
   OPENAI_API_KEY=your_openai_api_key
   AMADEUS_CLIENT_ID=your_amadeus_client_id
   AMADEUS_CLIENT_SECRET=your_amadeus_client_secret
   ```

4. **Run the Application**Start the FastAPI server:

   ```bash
   uvicorn main:app --reload
   ```

## Usage

### API Endpoints

- **GET** `/`

  - Returns a welcome message: `{"message": "Flight Search Chatbot API v2.0 is running"}`

- **GET** `/health`

  - Checks server and API key status.
  - Response: `{"status": "healthy", "message": "All API keys configured"}` or a warning if keys are missing.

- **POST** `/api/chat`

  - Handles chat requests with a JSON body:

    ```json
    {
      "thread_id": "unique_thread_id",
      "user_msg": "I want to fly from Cairo to Madrid on August 26, 2025 for 5 nights"
    }
    ```
  - Returns HTML content with travel packages or a follow-up question if more details are needed.

- **POST** `/api/reset/{thread_id}`

  - Resets conversation history for the given `thread_id`.
  - Response: `{"message": "Conversation for thread {thread_id} has been reset"}`

- **GET** `/api/threads`

  - Lists all active conversation threads.
  - Response: `{"threads": ["thread1", "thread2"], "count": 2}`

### Example Interaction

1. Send a POST request to `/api/chat` with:

   ```json
   {
     "thread_id": "thread1",
     "user_msg": "I want to fly from Cairo to Madrid on August 26, 2025 for 5 nights"
   }
   ```
2. Receive a follow-up question (e.g., "Please specify your cabin class").
3. Respond with updated details and eventually get HTML with travel packages.

## Development

### Running Tests

Add test cases in a `tests/` directory (not currently present). Example:

```bash
pytest tests/
```

### Adding New Nodes

- Create a new file in `Nodes/` (e.g., `new_node.py`).
- Import and add the node to `graph.py` using `graph.add_node`.
- Update the graph edges in `create_travel_graph` to include the new node.
 - For LLM access in nodes, import `llm` from `Utils.watson_config`.
 - For visa search, see `Nodes/visa_rag_node.py` and `Utils/build_vector_store.py`.

### Debugging

- Enable logging by checking `main.py` logs.
- Use print statements in node functions for detailed tracing.

## Acknowledgments

- **Amadeus API**: For travel data.
- **IBM watsonx.ai**: Primary LLM for generation.
- **OpenAI**: Embeddings for visa RAG and FAISS vector store.
- **LangGraph**: For workflow management.
- **FastAPI**: For the API framework.