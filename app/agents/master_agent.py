import os
import google.generativeai as genai
import logging
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv # <-- IMPORT ADDED

# Import our custom tools
from app.agents.tools import verification_tool, underwriting_tool, sanction_letter_tool
from app.models.data_models import CustomerProfile

# --- Load .env file BEFORE doing anything else ---
load_dotenv() # <-- LINE ADDED
# This will load the .env file into os.environ for local dev

# Configure logging
logger = logging.getLogger(__name__)

# --- AGENT CONFIGURATION ---

# 1. Load the API Key
try:
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("Gemini API Key loaded.")
except KeyError:
    logger.critical("GEMINI_API_KEY environment variable not set. Agent cannot start.")
    GEMINI_API_KEY = None # Handle for startup

# 2. Define the System Prompt (This is the "Agentic Logic")
# This is the most critical part of the AI.
# It tells the agent WHO it is and WHAT its rules are.
MASTER_SYSTEM_PROMPT = """
You are "CredFlow", a senior loan processing agent for a digital bank.
Your goal is to guide a customer through a personal loan application, from
verification to a final decision.

You MUST follow these rules STRICTLY:

1.  **Greet & Verify:** Start by greeting the user. Your VERY FIRST action
    must be to ask for their 10-digit phone number to verify them.
    You cannot discuss anything else until they are verified.

2.  **Call Verification:** Once you have the phone number, you MUST call
    the `verification_tool`.
    - IF `status` is "error" (e.g., not found, KYC not verified), you MUST
      politely inform the user of the error message and STOP the process.
    - IF `status` is "success", you have verified the user. Address them
      by their name (from the tool's 'data' payload) and proceed.

3.  **Gather Loan Details:** After verification, ask the user for:
    a) The loan amount they need.
    b) The loan tenure in months.

4.  **Call Underwriting:** Once you have the amount and tenure, you MUST
    call the `underwriting_tool`.
    - You MUST pass all required arguments: `annual_income`,
      `existing_emis`, `bureau_score` (from the verified customer data),
      AND the `requested_amount` and `requested_tenure_months` from the user.

5.  **Deliver the Decision:**
    - The `underwriting_tool` will return a "status" ("approved",
      "rejected", or "needs_review").
    - You MUST clearly state this decision and the "message" from the tool.
    - DO NOT make up your own decision or numbers.

6.  **Call Sanction Letter (on Approval):**
    - IF the status is "approved", you MUST then immediately call the
      `sanction_letter_tool` to generate the PDF.
    - You MUST pass the customer's name and the approved loan details
      (amount, tenure, new_emi) from the underwriting tool's 'data' payload.
    - After calling the tool, present the final "message" and the "pdf_url"
      to the user. This is the final step.

Maintain a professional, helpful, and concise tone.
"""

# 3. Initialize the Gemini Model
# We configure the model to use our Python functions as "tools"
# These are the *only* functions the model can decide to call.
AVAILABLE_TOOLS = [
    verification_tool,
    underwriting_tool,
    sanction_letter_tool
]

# Set up the model
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=MASTER_SYSTEM_PROMPT,
    tools=AVAILABLE_TOOLS
)

# --- CONVERSATION LOGIC ---

# This list will store the full chat history *in the format Gemini expects*
# We will pass this to the FastAPI app later
chat_sessions: Dict[str, genai.ChatSession] = {}

def get_chat_session(session_id: str) -> genai.ChatSession:
    """
    Retrieves or creates a new chat session by ID.
    This allows uss to maintain separate conversations for different users.
    """
    if session_id not in chat_sessions:
        logger.info(f"Creating new chat session: {session_id}")
        chat_sessions[session_id] = model.start_chat(enable_automatic_function_calling=True)
    return chat_sessions[session_id]

async def run_conversation_turn(
    session_id: str, 
    user_message: str
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Runs a single turn of the conversation.
    This is the main function our FastAPI will call.

    Args:
        session_id: A unique ID for the user's session.
        user_message: The raw text from the user.

    Returns:
        A tuple containing:
        1.  final_response (str): The agent's final text message to the user.
        2.  trace (List[Dict]): A step-by-step trace of the agent's thoughts
            and tool calls, for our dashboard.
    """
    if not GEMINI_API_KEY:
        return "Error: Agent is not configured. Missing API Key.", []

    trace = [] # This will store our "Agent Command Center" data
    
    try:
        # 1. Get the user's chat session
        chat = get_chat_session(session_id)
        
        # 2. Send the user's message to Gemini
        # We use send_message_async for performance
        logger.info(f"[{session_id}] User said: '{user_message}'")
        trace.append({"role": "user", "message": user_message})
        
        response = await chat.send_message_async(user_message)
        
        # 3. Check the response and handle tool calls
        # The 'enable_automatic_function_calling=True' handles the loop
        # for us. The model will call tools and re-prompt itself
        # until it has a final text answer.
        
        # 4. Log the full trace for our dashboard
        # We review the history to show what the agent did.
        for part in response.candidates[0].content.parts:
            if part.function_call:
                trace.append({
                    "role": "agent_thought",
                    "thought": f"Calling tool: {part.function_call.name}",
                    "tool_call": {
                        "name": part.function_call.name,
                        "args": dict(part.function_call.args)
                    }
                })
            elif part.function_response:
                trace.append({
                    "role": "tool_response",
                    "tool_response": {
                        "name": part.function_response.name,
                        "response": dict(part.function_response.response)
                    }
                })
            elif part.text:
                trace.append({"role": "agent_response", "message": part.text})

        # 5. Get the final text response
        final_response = response.candidates[0].content.parts[-1].text
        logger.info(f"[{session_id}] Agent responded: '{final_response}'")
        
        return final_response, trace

    except Exception as e:
        logger.error(f"Error during conversation turn: {e}", exc_info=True)
        return f"An internal error occurred: {e}", trace