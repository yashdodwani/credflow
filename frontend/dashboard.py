import streamlit as st
import httpx
import uuid
import os
import json
import time
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="CredFlow Agent Command Center",
    page_icon="🤖",
    layout="wide"
)

# --- Custom CSS for Better UI ---
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
    }
    .stat-card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 4px solid #667eea;
    }
    .agent-step {
        background: #f8f9fa;
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
        border-left: 3px solid #28a745;
    }
    .agent-thinking {
        background: #fff3cd;
        padding: 10px;
        border-radius: 5px;
        margin: 5px 0;
        font-style: italic;
    }
    .success-badge {
        background: #28a745;
        color: white;
        padding: 5px 10px;
        border-radius: 15px;
        font-size: 12px;
    }
    .error-badge {
        background: #dc3545;
        color: white;
        padding: 5px 10px;
        border-radius: 15px;
        font-size: 12px;
    }
    .pending-badge {
        background: #ffc107;
        color: white;
        padding: 5px 10px;
        border-radius: 15px;
        font-size: 12px;
    }
    .progress-trail {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 30px 40px;
        background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
        border-radius: 15px;
        margin: 20px 0;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        position: relative;
        overflow: hidden;
    }
    .progress-trail::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, #28a745, #20c997, #17a2b8);
        opacity: 0.5;
    }
    .stage {
        display: flex;
        flex-direction: column;
        align-items: center;
        flex: 1;
        position: relative;
        z-index: 3;
    }
    .stage-circle {
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: linear-gradient(145deg, #2a2a2a, #1f1f1f);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 26px;
        border: 3px solid #3a3a3a;
        transition: all 0.4s cubic-bezier(0.68, -0.55, 0.265, 1.55);
        box-shadow: 
            0 4px 15px rgba(0,0,0,0.4),
            inset 0 2px 4px rgba(255,255,255,0.1);
        position: relative;
        cursor: pointer;
    }
    .stage-circle:hover {
        transform: translateY(-3px) scale(1.05);
        box-shadow: 
            0 8px 25px rgba(0,0,0,0.5),
            inset 0 2px 4px rgba(255,255,255,0.15);
    }
    .stage-circle.completed {
        background: linear-gradient(145deg, #28a745, #20c997);
        border-color: #28a745;
        animation: completePulse 0.6s ease;
        box-shadow: 
            0 0 20px rgba(40, 167, 69, 0.6),
            0 4px 15px rgba(0,0,0,0.4),
            inset 0 2px 4px rgba(255,255,255,0.2);
    }
    .stage-circle.completed::after {
        content: '';
        position: absolute;
        width: 100%;
        height: 100%;
        border-radius: 50%;
        border: 2px solid #28a745;
        animation: ripple 1.5s ease-out infinite;
    }
    @keyframes completePulse {
        0% { transform: scale(0.8); opacity: 0.5; }
        50% { transform: scale(1.15); }
        100% { transform: scale(1); opacity: 1; }
    }
    @keyframes ripple {
        0% {
            transform: scale(1);
            opacity: 1;
        }
        100% {
            transform: scale(1.4);
            opacity: 0;
        }
    }
    .stage-label {
        margin-top: 12px;
        font-size: 13px;
        font-weight: 600;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        transition: all 0.3s ease;
    }
    .stage-label.completed {
        color: #28a745;
        text-shadow: 0 0 10px rgba(40, 167, 69, 0.3);
    }
    .stage-connector {
        height: 4px;
        background: linear-gradient(90deg, #2a2a2a, #3a3a3a);
        flex: 1;
        margin: 0 -15px;
        position: relative;
        top: -38px;
        z-index: 1;
        border-radius: 2px;
        box-shadow: inset 0 1px 3px rgba(0,0,0,0.5);
    }
    .stage-connector.completed {
        background: linear-gradient(90deg, #28a745, #20c997);
        box-shadow: 
            0 0 15px rgba(40, 167, 69, 0.5),
            inset 0 1px 3px rgba(255,255,255,0.2);
        animation: flowProgress 1s ease forwards;
    }
    @keyframes flowProgress {
        0% {
            transform: scaleX(0);
            transform-origin: left;
        }
        100% {
            transform: scaleX(1);
        }
    }
    .stage-number {
        position: absolute;
        top: -8px;
        right: -8px;
        width: 24px;
        height: 24px;
        background: linear-gradient(145deg, #667eea, #764ba2);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: bold;
        color: white;
        box-shadow: 0 2px 8px rgba(102, 126, 234, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# --- Backend API URL ---
API_BASE_URL = os.environ.get("API_URL", "http://localhost:8080")
CHAT_ENDPOINT = f"{API_BASE_URL}/chat"

# --- Session State Management ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.last_trace = None
    st.session_state.agent_steps = []
    st.session_state.progress_stages = {"verification": False, "underwriting": False, "sanction": False}

# --- Dummy Analytics Data ---
TOTAL_APPLICATIONS = 247
APPROVED_LOANS = 168
REJECTED_LOANS = 62
UNDER_REVIEW = 17
TOTAL_DISBURSED = 42500000  # in INR
AVG_LOAN_AMOUNT = 253000
AVG_PROCESSING_TIME = 3.2  # minutes

# --- Helper Function to Parse Trace into Agent Steps ---
def parse_trace_to_steps(trace):
    """Convert the trace JSON into human-readable agent workflow steps"""
    steps = []
    current_stage = {"verification": False, "underwriting": False, "sanction": False}
    
    for item in trace:
        if item.get("role") == "user":
            steps.append({
                "type": "user_input",
                "message": item.get("message", ""),
                "icon": "👤"
            })
        
        elif item.get("role") == "agent_thought":
            tool_name = item.get("tool_call", {}).get("name", "")
            tool_args = item.get("tool_call", {}).get("args", {})
            
            if "verification" in tool_name:
                steps.append({
                    "type": "agent_action",
                    "agent": "Master Agent",
                    "action": f"🔍 Delegating to **Verification Agent**",
                    "details": f"Task: Verify customer with phone: {tool_args.get('phone_number', 'N/A')}",
                    "icon": "🤖"
                })
                steps.append({
                    "type": "agent_working",
                    "agent": "Verification Agent",
                    "action": "⚙️ Processing verification request...",
                    "details": "→ Connecting to Firestore database\n→ Querying customer records\n→ Validating KYC status\n→ Retrieving customer profile data",
                    "icon": "🔐"
                })
            
            elif "underwriting" in tool_name:
                steps.append({
                    "type": "agent_action",
                    "agent": "Master Agent",
                    "action": f"📊 Delegating to **Underwriting Agent**",
                    "details": f"Task: Evaluate loan of ₹{tool_args.get('requested_amount', 'N/A'):,} for {tool_args.get('requested_tenure_months', 'N/A')} months",
                    "icon": "🤖"
                })
                steps.append({
                    "type": "agent_working",
                    "agent": "Underwriting Agent",
                    "action": "⚙️ Running credit assessment...",
                    "details": f"→ Checking bureau score: {tool_args.get('bureau_score', 'N/A')}\n→ Analyzing annual income: ₹{tool_args.get('annual_income', 'N/A'):,}\n→ Evaluating existing EMIs: ₹{tool_args.get('existing_emis', 'N/A'):,}\n→ Calculating FOIR (Fixed Obligation to Income Ratio)\n→ Running credit policy rules",
                    "icon": "💳"
                })
            
            elif "sanction_letter" in tool_name:
                steps.append({
                    "type": "agent_action",
                    "agent": "Master Agent",
                    "action": f"📄 Delegating to **Sanction Letter Agent**",
                    "details": f"Task: Generate PDF for {tool_args.get('customer_name', 'N/A')}",
                    "icon": "🤖"
                })
                steps.append({
                    "type": "agent_working",
                    "agent": "Sanction Letter Agent",
                    "action": "⚙️ Creating sanction letter...",
                    "details": f"→ Generating PDF document with loan terms\n→ Adding customer details and loan amount\n→ Uploading to Google Cloud Storage\n→ Creating secure public access link",
                    "icon": "📝"
                })
        
        elif item.get("role") == "tool_response":
            tool_name = item.get("tool_response", {}).get("name", "")
            response = item.get("tool_response", {}).get("response", {})
            status = response.get("status", "unknown")
            
            agent_name = "Unknown Agent"
            stage_key = None
            if "verification" in tool_name:
                agent_name = "Verification Agent"
                stage_key = "verification"
            elif "underwriting" in tool_name:
                agent_name = "Underwriting Agent"
                stage_key = "underwriting"
            elif "sanction_letter" in tool_name:
                agent_name = "Sanction Letter Agent"
                stage_key = "sanction"
            
            if stage_key and status == "success":
                current_stage[stage_key] = True
            
            status_icon = "✅" if status == "success" else "❌" if status == "error" else "⚠️"
            
            steps.append({
                "type": "agent_result",
                "agent": agent_name,
                "action": f"{status_icon} Task completed: **{status.upper()}**",
                "details": response.get("message", "No details available"),
                "icon": "📋",
                "status": status
            })
        
        elif item.get("role") == "agent_response":
            steps.append({
                "type": "final_response",
                "message": item.get("message", ""),
                "icon": "💬"
            })
    
    return steps, current_stage

# --- App Header ---
st.markdown("""
<div class="main-header">
    <h1>🤖 CredFlow BFSI Agent</h1>
    <p>Real-time monitoring of AI-powered autonomous loan processing system</p>
</div>
""", unsafe_allow_html=True)

# --- Top Stats Bar ---
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Total Applications", f"{TOTAL_APPLICATIONS}", "+12 today")
with col2:
    approval_rate = (APPROVED_LOANS / TOTAL_APPLICATIONS) * 100
    st.metric("Approval Rate", f"{approval_rate:.1f}%", "↑ 2.3%")
with col3:
    st.metric("Approved Loans", f"{APPROVED_LOANS}", "+8 today")
with col4:
    st.metric("Total Disbursed", f"₹{TOTAL_DISBURSED/10000000:.1f}Cr", "+₹42L today")
with col5:
    st.metric("Avg. Processing", f"{AVG_PROCESSING_TIME} min", "↓ 0.5 min")

st.markdown("---")

# --- Main Layout (2 Columns) ---
col_chat, col_dashboard = st.columns([1, 1])

# --- Column 1: The Chat Interface ---
with col_chat:
    st.subheader("💬 Customer Interaction Panel")
    
    # Display existing chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input box
    if prompt := st.chat_input("Type your message here..."):
        
        # Add user's message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Call the FastAPI backend
        try:
            with st.spinner("🤖 Agent is processing your request..."):
                payload = {
                    "session_id": st.session_state.session_id,
                    "message": prompt
                }
                
                with httpx.Client(timeout=120.0) as client:
                    response = client.post(CHAT_ENDPOINT, json=payload)
                
                response.raise_for_status()
                
                data = response.json()
                agent_response = data["agent_response"]
                st.session_state.last_trace = data["trace"]
                st.session_state.agent_steps, st.session_state.progress_stages = parse_trace_to_steps(data["trace"])
                
                st.session_state.messages.append({"role": "assistant", "content": agent_response})
                with st.chat_message("assistant"):
                    st.markdown(agent_response)

        except httpx.HTTPStatusError as e:
            st.error(f"❌ HTTP error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            st.error(f"❌ Connection error: Could not reach API. Is it running?")
        except Exception as e:
            st.error(f"❌ An unexpected error occurred: {e}")

        st.rerun()

# --- Column 2: Agent Workflow Dashboard ---
with col_dashboard:
    st.subheader("🧠 Agent Workflow Monitor")
    
    # Progress Trail
    st.markdown("### 🎯 Loan Processing Pipeline")
    
    verification_status = "completed" if st.session_state.progress_stages.get("verification", False) else ""
    underwriting_status = "completed" if st.session_state.progress_stages.get("underwriting", False) else ""
    sanction_status = "completed" if st.session_state.progress_stages.get("sanction", False) else ""
    
    connector1_status = "completed" if st.session_state.progress_stages.get("verification", False) else ""
    connector2_status = "completed" if st.session_state.progress_stages.get("underwriting", False) else ""
    
    st.markdown(f"""
    <div class="progress-trail">
        <div class="stage">
            <div class="stage-circle {verification_status}">
                {"✓" if verification_status else "🔐"}
            </div>
            <div class="stage-label {verification_status}">Verification</div>
        </div>
        <div class="stage-connector {connector1_status}"></div>
        <div class="stage">
            <div class="stage-circle {underwriting_status}">
                {"✓" if underwriting_status else "💳"}
            </div>
            <div class="stage-label {underwriting_status}">Underwriting</div>
        </div>
        <div class="stage-connector {connector2_status}"></div>
        <div class="stage">
            <div class="stage-circle {sanction_status}">
                {"✓" if sanction_status else "📝"}
            </div>
            <div class="stage-label {sanction_status}">Sanction Letter</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    if st.session_state.agent_steps:
        st.info(f"📍 Live Agent Activity | Session: {st.session_state.session_id[:8]}...")
        
        for step in st.session_state.agent_steps:
            if step["type"] == "user_input":
                with st.container():
                    st.markdown(f"**{step['icon']} User Input:**")
                    st.text(step['message'])
                    st.markdown("---")
            
            elif step["type"] == "agent_action":
                with st.container():
                    st.markdown(f"""
                    <div class="agent-step">
                        <strong>{step['icon']} {step['agent']}</strong><br/>
                        {step['action']}<br/>
                        <small style="color: #666;">{step['details']}</small>
                    </div>
                    """, unsafe_allow_html=True)
            
            elif step["type"] == "agent_working":
                with st.container():
                    st.markdown(f"""
                    <div class="agent-thinking">
                        <strong>{step['icon']} {step['agent']}</strong><br/>
                        {step['action']}<br/>
                        <small style="white-space: pre-line;">{step['details']}</small>
                    </div>
                    """, unsafe_allow_html=True)
            
            elif step["type"] == "agent_result":
                with st.container():
                    st.markdown(f"""
                    <div class="agent-step">
                        <strong>{step['icon']} {step['agent']}</strong><br/>
                        {step['action']}<br/>
                        <small style="color: #666;">{step['details']}</small>
                    </div>
                    """, unsafe_allow_html=True)
            
            elif step["type"] == "final_response":
                with st.container():
                    st.success(f"**{step['icon']} Final Response Generated**")
                    st.markdown("---")
    
    else:
        st.info("🎯 Agent workflow visualization will appear here once you start chatting.")
        st.markdown("""
        **The system will show:**
        - 🤖 Master Agent delegation decisions
        - 🔐 Verification Agent database checks
        - 💳 Underwriting Agent credit analysis
        - 📝 Sanction Letter Agent document generation
        """)

# --- Bottom Analytics Section ---
st.markdown("---")
st.subheader("📊 System Analytics & Performance")

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.markdown("### Loan Distribution")
    st.markdown(f"""
    - ✅ **Approved:** {APPROVED_LOANS} ({(APPROVED_LOANS/TOTAL_APPLICATIONS)*100:.1f}%)
    - ❌ **Rejected:** {REJECTED_LOANS} ({(REJECTED_LOANS/TOTAL_APPLICATIONS)*100:.1f}%)
    - ⏳ **Under Review:** {UNDER_REVIEW} ({(UNDER_REVIEW/TOTAL_APPLICATIONS)*100:.1f}%)
    """)

with col_b:
    st.markdown("### Financial Metrics")
    st.markdown(f"""
    - 💰 **Avg Loan Amount:** ₹{AVG_LOAN_AMOUNT:,}
    - 📈 **Highest Disbursement:** ₹8,00,000
    - 📉 **Lowest Disbursement:** ₹50,000
    - 🎯 **Default Rate:** 2.1%
    """)

with col_c:
    st.markdown("### Operational Stats")
    st.markdown(f"""
    - ⚡ **Avg Processing Time:** {AVG_PROCESSING_TIME} min
    - 🔄 **Active Sessions:** 23
    - 📅 **Applications Today:** 12
    - 🤖 **AI Accuracy:** 94.3%
    """)