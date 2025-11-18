import logging
from fpdf import FPDF
from datetime import datetime
from google.cloud import storage
from typing import Dict, Any

from app.database.firestore_db import get_customer_by_phone
from app.models.data_models import CustomerProfile, AgentToolResponse

# Configure logging
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---

GCS_BUCKET_NAME = "credflow-sanction-letters-bucket" 
CREDIT_POLICY_MIN_SCORE = 700
CREDIT_POLICY_MAX_FOIR = 0.50  # 50% Fixed Obligation to Income Ratio

# --- 1. VERIFICATION AGENT ---

def verification_tool(phone_number: str) -> Dict[str, Any]:
    """
    Verifies a customer by checking if they exist in the Firestore CRM.
    
    Args:
        phone_number: The customer's 10-digit phone number.

    Returns:
        A dictionary with status and data/message.
    """
    logger.info(f"VERIFICATION_TOOL: Running for phone: {phone_number}")
    if not phone_number or len(phone_number) != 10 or not phone_number.isdigit():
        return AgentToolResponse(
            status="error",
            message="Invalid phone number. Please provide a valid 10-digit number."
        ).dict()

    customer = get_customer_by_phone(phone_number)
    
    if not customer:
        return AgentToolResponse(
            status="error",
            message=f"No customer profile found for {phone_number}. We cannot proceed."
        ).dict()
    
    if not customer.kyc_verified:
        return AgentToolResponse(
            status="error",
            message=f"Customer {customer.full_name} found, but KYC is not verified. Please complete KYC."
        ).dict()

    return AgentToolResponse(
        status="success",
        message=f"Successfully verified customer: {customer.full_name}",
        data=customer.dict()
    ).dict()


# --- 2. UNDERWRITING AGENT ---

def underwriting_tool(
    annual_income: int, 
    existing_emis: int, 
    bureau_score: int, 
    requested_amount: int,
    requested_tenure_months: int
) -> Dict[str, Any]:
    """
    Performs credit underwriting based on defined credit policy.
    
    Args:
        annual_income: Customer's annual income.
        existing_emis: Customer's existing monthly EMI payments.
        bureau_score: Customer's credit score (0-900).
        requested_amount: The loan amount requested.
        requested_tenure_months: The loan tenure in months.

    Returns:
        A dictionary with approval/rejection status and reasoning.
    """
    logger.info(f"UNDERWRITING_TOOL: Running for amount {requested_amount}")
    
    # Policy 1: Check Bureau Score
    if bureau_score < CREDIT_POLICY_MIN_SCORE:
        if bureau_score == 0: # Handle "New to Credit"
            return AgentToolResponse(
                status="needs_review",
                message="Customer is new to credit (Score: 0). Forwarding for manual underwriting."
            ).dict()
        return AgentToolResponse(
            status="rejected",
            message=f"Loan rejected. Credit score ({bureau_score}) is below the minimum required ({CREDIT_POLICY_MIN_SCORE})."
        ).dict()

    # Policy 2: Calculate FOIR (Fixed Obligation to Income Ratio)
    # Assuming a sample interest rate of 12% p.a. for EMI calculation
    # This is a simple EMI formula. R = (P * r * (1+r)^n) / ((1+r)^n - 1)
    # We will approximate this for the demo. A real app would have a proper calculator.
    # Let's use a simple approximation for this demo to avoid complex math libs
    # Let's assume a flat 12% p.a. interest (1% per month)
    # A simple estimate: total interest = P * r * n (simple interest)
    # A slightly better approximation for EMI:
    
    monthly_income = annual_income / 12
    
    # Simplified EMI calculation (approximation)
    # This is NOT a real EMI formula, but good enough for demo logic
    # Real formula is P * r * (1+r)^n / ((1+r)^n - 1)
    # Let's just calculate based on a flat 12% rate (0.01/month)
    # We will estimate total monthly payment (new + old)
    # Simple FOIR: (existing_emis + new_loan_emi) / monthly_income
    
    # Simplified New EMI (using a flat 14% p.a. or ~1.17% per month rate approx)
    # This is a simplified "factor" based estimation for demo
    interest_rate_monthly = 0.14 / 12
    if requested_tenure_months == 0: requested_tenure_months = 12 # avoid division by zero
    
    try:
        # P * [r(1+r)^n] / [(1+r)^n-1]
        r = interest_rate_monthly
        n = requested_tenure_months
        P = requested_amount
        
        if r > 0:
            new_emi = (P * r * (1 + r)**n) / ((1 + r)**n - 1)
        else:
            new_emi = P / n # Simple fallback for 0 interest
            
        new_emi = round(new_emi)
    except Exception:
        new_emi = (requested_amount * 1.14) / requested_tenure_months # Failsafe
    
    
    total_emis = existing_emis + new_emi
    
    # Calculate FOIR
    foir = total_emis / monthly_income
    
    logger.info(f"UNDERWRITING_TOOL: Monthly Income: {monthly_income}, New EMI: {new_emi}, Total EMIs: {total_emis}, FOIR: {foir}")

    if foir > CREDIT_POLICY_MAX_FOIR:
        return AgentToolResponse(
            status="rejected",
            message=f"Loan rejected. Your Fixed Obligation to Income Ratio (FOIR) would be {foir*100:.0f}%, which is above the {CREDIT_POLICY_MAX_FOIR*100:.0f}% limit."
        ).dict()

    # All checks passed!
    return AgentToolResponse(
        status="approved",
        message=f"Congratulations! Your loan for {requested_amount} is approved. Your FOIR is {foir*100:.0f}%.",
        data={"approved_amount": requested_amount, "tenure": requested_tenure_months, "new_emi": new_emi}
    ).dict()


# --- 3. SANCTION LETTER AGENT ---

def sanction_letter_tool(customer_name: str, approved_amount: int, tenure: int, new_emi: int) -> Dict[str, Any]:
    """
    Generates a PDF sanction letter and uploads it to Google Cloud Storage.
    
    Args:
        customer_name: Full name of the customer.
        approved_amount: The loan amount that was approved.
        tenure: The loan tenure in months.
        new_emi: The calculated EMI for the new loan.

    Returns:
        A dictionary with status and the public URL of the PDF.
    """
    logger.info(f"SANCTION_TOOL: Generating PDF for {customer_name}")
    
    try:
        # 1. Create PDF locally in memory
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=16)
        
        # Title
        pdf.cell(200, 10, txt="Loan Sanction Letter", ln=True, align='C')
        pdf.ln(10) # Add a break
        
        # Body
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, f"Date: {datetime.now().strftime('%Y-%m-%d')}\n\n"
                               f"Dear {customer_name},\n\n"
                               f"We are pleased to inform you that your personal loan application has been approved.\n\n"
                               "Here are the details of your sanction:\n")
        
        pdf.ln(5)
        pdf.set_font("Arial", 'B', size=12)
        pdf.cell(0, 10, f"Approved Loan Amount: INR {approved_amount:,.2f}", ln=True)
        pdf.cell(0, 10, f"Loan Tenure: {tenure} months", ln=True)
        pdf.cell(0, 10, f"Equated Monthly Installment (EMI): INR {new_emi:,.2f}", ln=True)
        pdf.cell(0, 10, f"Interest Rate: 14% p.a. (reducing)", ln=True) # Hardcoded for demo
        
        pdf.ln(10)
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 10, "This offer is valid for 7 days. Please contact us to complete the disbursal process.\n\n"
                               "We look forward to serving you.\n\n"
                               "Sincerely,\n"
                               "The CrediFlow Team")

        # Define file paths
        local_filename = f"/tmp/sanction_letter_{customer_name.replace(' ','_')}.pdf"
        gcs_blob_name = f"sanction_letters/{customer_name.replace(' ','_')}_{datetime.now().strftime('%Y%m%d%H%M')}.pdf"

        pdf.output(local_filename)

        # 2. Upload to GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(gcs_blob_name)
        
        blob.upload_from_filename(local_filename)
        
        # 3. Make it public (for the demo)
        blob.make_public()
        public_url = blob.public_url

        logger.info(f"SANCTION_TOOL: Successfully uploaded PDF to {public_url}")
        
        return AgentToolResponse(
            status="success",
            message=f"Sanction letter has been generated and uploaded.",
            data={"pdf_url": public_url}
        ).dict()
        
    except Exception as e:
        logger.error(f"SANCTION_TOOL: Failed to generate or upload PDF. Error: {e}")
        return AgentToolResponse(
            status="error",
            message=f"An internal error occurred while generating the PDF sanction letter: {e}"
        ).dict()