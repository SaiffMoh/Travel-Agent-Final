# Travel Agent API

Welcome to the **Travel Agent API**, an AI-powered flight and hotel search assistant built with FastAPI and LangGraph. This application allows users to interact with a conversational AI to search for flight and hotel packages, leveraging the Amadeus API for travel data, IBM watsonx.ai as the primary LLM, and OpenAI embeddings for the visa RAG component.

---

## Overview

The Travel Agent API is designed to:
- Process user queries via a chat interface.
- Extract travel preferences (e.g., departure date, origin, destination, cabin class, duration).
- Fetch flight and hotel offers using the Amadeus API.
- Create travel packages combining flights and hotels.
- Generate HTML summaries of available packages.
- **Fallback to a local database** if the Amadeus API is unavailable.
- **Use LLM-based fallback** for queries outside the database scope.
- **Generate realistic dummy data** if both the API and database fail.

The application uses a stateful graph-based workflow managed by LangGraph, with nodes handling specific tasks like conversation analysis, API calls, and package creation.

---

## Features

- **Conversational Interface**: Users can interact via a thread-based chat system.
- **Flight Search**: Retrieves flight offers for three consecutive days using the Amadeus API.
- **Hotel Search**: Fetches hotel offers based on flight-derived check-in and check-out dates.
- **Package Creation**: Combines flight and hotel data into travel packages.
- **HTML Output**: Generates formatted HTML for package summaries.
- **API Health Check**: Monitors API key availability and server status.
- **Conversation Reset**: Allows resetting conversation history by thread ID.
- **Visa Requirements (RAG)**: Answers visa questions using a FAISS vector store built with OpenAI embeddings and generates responses with IBM watsonx.ai.
- **Multi-Layer Fallback**: Database → LLM-based fallback → Rule-based dummy data.

---

## Fallback Flow

The Travel Agent API includes a **three-layer fallback system** to ensure users always receive travel package suggestions, even if the Amadeus API is unavailable or the query is out of scope.

### **1. Database Fallback**
- If the Amadeus API fails or is unavailable, the system falls back to a **local SQLite database** (`travel_data.db`).
- The database contains pre-collected flight and hotel data for specific routes, dates, and cabin classes.
- **Example:** If you query "Cairo to Algiers on November 2, 2025, for 5 nights in economy class," the system retrieves matching data from the database.

### **2. LLM-Based Fallback**
- If the query is **outside the database scope** (e.g., a destination, date, or cabin class not in the database), the system uses **IBM watsonx.ai** to generate realistic flight and hotel offers.
- The LLM generates data based on real schema templates and realistic pricing.
- **Example:** If you query "Cairo to Paris on December 1, 2025, for 7 nights in business class," the system generates synthetic but realistic flight and hotel offers.

### **3. Rule-Based Fallback**
- If both the Amadeus API and LLM-based fallback fail, the system generates **rule-based dummy data** for flights and hotels.
- This ensures users always receive a response, even in edge cases.

---

## Travel Data Fallback – Query Options

You can use any of the following options when making a query to retrieve data from the fallback database (`travel_data.db`). To access it in the `.env`, add key:
`USE_FALLBACK=true`
Set it to `false` if you want to use the actual Amadeus API.

### **Sample Query Format**
```
I want to fly from Cairo to [DESTINATION] on [DEPARTURE_DATE] for [DURATION] nights in [CABIN_CLASS].
```

### **Available Destinations**
| Destination | Code |
|-------------|------|
| Dubai       | DXB  |
| Algiers     | ALG  |
| Riyadh      | RUH  |
| Abu Dhabi   | AUH  |
| Barcelona   | BCN  |
| Madrid      | MAD  |

### **Available Departure Dates**
| Date               |
|--------------------|
| October 30, 2025   |
| November 2, 2025   |
| November 5, 2025   |
| November 8, 2025   |
| November 11, 2025  |

### **Available Durations**
| Duration   |
|------------|
| 3 nights   |
| 5 nights   |
| 7 nights   |

### **Available Cabin Classes by Destination**
| Destination | Economy | Business |
|-------------|---------|----------|
| Dubai (DXB) | ✓       | ✓        |
| Algiers (ALG)| ✓       | ✓        |
| Riyadh (RUH)| ✓       | ✓        |
| Abu Dhabi (AUH)| ✓     | ✓        |
| Barcelona (BCN)| ✓     | ✓        |
| Madrid (MAD)| ✓       | ✓        |

---

### **Database Statistics**
#### **Total Data Available**
- **Total Flights:** 750 offers across 6 destinations
- **Total Hotel Searches:** 148+
- **Cabin Classes:** Economy and Business
- **Cities with Hotels:** 5 (ALG, RUH, AUH, MAD, and partial DXB coverage)

#### **Flights by Destination**
| Route       | Economy | Business | Total |
|-------------|---------|----------|-------|
| CAI → DXB   | 75      | 75       | 150   |
| CAI → ALG   | 75      | 75       | 150   |
| CAI → RUH   | 75      | 75       | 150   |
| CAI → AUH   | 75      | 75       | 150   |
| CAI → BCN   | 75      | 75       | 150   |
| CAI → MAD   | 75      | 75       | 150   |

#### **Hotel Availability**
| City | Hotels Available |
|------|------------------|
| DXB  | No               |
| ALG  | Yes (2 per search)|
| RUH  | Yes (1-2 per search)|
| AUH  | Yes (2-3 per search)|
| BCN  | No               |
| MAD  | Yes (3-4 per search)|

---

### **Example Queries**
#### **Economy Class**
- I want to fly from Cairo to Riyadh on November 2, 2025, for 5 nights in economy class.
- I want to fly from Cairo to Abu Dhabi on November 8, 2025, for 7 nights in economy class.
- I want to fly from Cairo to Algiers on October 30, 2025, for 3 nights in economy class.

#### **Business Class**
- I want to fly from Cairo to Dubai on November 2, 2025, for 7 nights in business class.
- I want to fly from Cairo to Riyadh on November 8, 2025, for 5 nights in business class.

---

### **Out-of-Scope Queries**
For queries **not covered by the database** (e.g., destinations like Paris, New York, or dates outside the database range), the system uses **LLM-based fallback** to generate realistic flight and hotel offers.

**Example:**
- I want to fly from Cairo to Paris on December 1, 2025, for 7 nights in business class.

---

## Data Collection Details
- **Date Range:** 7-22 days from the current date (rolling window)
- **Search Interval:** Every 3 days
- **Trip Durations:** 3, 5, and 7 nights
- **Flights per Search:** Up to 5 offers
- **Hotels per City:** Up to 10 hotels per search

---

## Directory Structure
```
Travel-Agent-Final/
├── Nodes/                       # Core workflow nodes
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

---

## Prerequisites
- **Python 3.9+**
- **Amadeus API Credentials**: `AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET`
- **IBM watsonx.ai Credentials**: `WATSON_APIKEY`, `PROJECT_ID`
- **OpenAI API Key (for embeddings)**: `OPENAI_API_KEY`

---

## Setup
1. **Clone the Repository**
   ```bash
   git clone https://github.com/SaiffMoh/Travel-Agent-Final.git
   cd Travel-Agent-Final
   ```

2. **Install Dependencies**
   Create a virtual environment and install required packages:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirments.txt
   ```

3. **Configure Environment Variables**
   Create a `.env` file in the project root with the following:
   ```
   # IBM watsonx.ai (primary LLM)
   WATSON_APIKEY=your_watson_api_key
   PROJECT_ID=your_watson_project_id
   # OpenAI (embeddings for visa RAG)
   OPENAI_API_KEY=your_openai_api_key
   # Amadeus API
   AMADEUS_CLIENT_ID=your_amadeus_client_id
   AMADEUS_CLIENT_SECRET=your_amadeus_client_secret
   # Fallback mode
   USE_FALLBACK=true
   ```

4. **Run the Application**
   Start the FastAPI server:
   ```bash
   uvicorn main\:app --reload
   ```

---

## Usage
### **API Endpoints**
- **GET** `/`
  Returns a welcome message: `{"message": "Flight Search Chatbot API v2.0 is running"}`

- **GET** `/health`
  Checks server and API key status.

- **POST** `/api/chat`
  Handles chat requests with a JSON body:
  ```json
  {
    "thread_id": "unique_thread_id",
    "user_msg": "I want to fly from Cairo to Madrid on August 26, 2025 for 5 nights"
  }
  ```
  Returns HTML content with travel packages or a follow-up question if more details are needed.

- **POST** `/api/reset/{thread_id}`
  Resets conversation history for the given `thread_id`.

- **GET** `/api/threads`
  Lists all active conversation threads.

---

### **Example Interaction**
1. Send a POST request to `/api/chat` with:
   ```json
   {
     "thread_id": "thread1",
     "user_msg": "I want to fly from Cairo to Madrid on August 26, 2025 for 5 nights"
   }
   ```
2. Receive a follow-up question (e.g., "Please specify your cabin class").
3. Respond with updated details and eventually get HTML with travel packages.

---

## Development
### **Running Tests**
Add test cases in a `tests/` directory (not currently present). Example:
```bash
pytest tests/
```

### **Adding New Nodes**
- Create a new file in `Nodes/` (e.g., `new_node.py`).
- Import and add the node to `graph.py` using `graph.add_node`.
- Update the graph edges in `create_travel_graph` to include the new node.

### **Debugging**
- Enable logging by checking `main.py` logs.
- Use print statements in node functions for detailed tracing.

---

## Acknowledgments
- **Amadeus API**: For travel data.
- **IBM watsonx.ai**: Primary LLM for generation.
- **OpenAI**: Embeddings for visa RAG and FAISS vector store.
- **LangGraph**: For workflow management.
- **FastAPI**: For the API framework.
