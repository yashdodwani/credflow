import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import uuid

# Import our master agent's conversation logic
from app.agents.master_agent import run_conversation_turn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="CredFlow Agent API",
    description="API for the Agentic Loan Processing System",
    version="1.0.0"
)

# --- CORS Middleware ---
# This is crucial for allowing our Streamlit frontend
# to call this API, especially when testing locally.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows all origins (for demo/simplicity)
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods
    allow_headers=["*"], # Allows all headers
)

# --- API Request & Response Models ---

class ChatRequest(BaseModel):
    session_id: str | None = None # Allow session ID to be optional
    message: str

class ChatResponse(BaseModel):
    session_id: str
    agent_response: str
    trace: List[Dict[str, Any]]

# --- API Endpoints ---

@app.get("/health", tags=["Status"])
async def get_health():
    """
    Simple health check endpoint for Cloud Run to verify the service is up.
    """
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse, tags=["Agent"])
async def handle_chat(request: ChatRequest):
    """
    Main endpoint to interact with the CrediFlow Master Agent.
    
    It manages a conversation session and returns the agent's
    text response plus a detailed trace of its actions.
    """
    try:
        # 1. Manage Session ID
        session_id = request.session_id or str(uuid.uuid4())
        logger.info(f"Received chat request for session: {session_id}")

        # 2. Run the conversation turn
        final_response, trace = await run_conversation_turn(
            session_id=session_id,
            user_message=request.message
        )
        
        # 3. Handle potential errors from the agent
        if "Error:" in final_response:
            raise HTTPException(status_code=500, detail=final_response)
        
        # 4. Return the successful response
        return ChatResponse(
            session_id=session_id,
            agent_response=final_response,
            trace=trace
        )

    except Exception as e:
        logger.error(f"Error in /chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")


# --- Run Locally ---
if __name__ == "__main__":
    """
    This allows you to run the API locally for testing:
    'python -m app.main'
    """
    uvicorn.run(app, host="0.0.0.0", port=8000)