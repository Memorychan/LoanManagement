# import os
# from datetime import datetime, timezone
# from dateutil.relativedelta import relativedelta
# from fastapi import FastAPI, HTTPException, Depends
# from fastapi.responses import FileResponse
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# from supabase import create_client, Client
# from dotenv import load_dotenv

# # --- CONFIGURATION ---
# load_dotenv()
# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# app = FastAPI(title="Crystal Ledger API")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"], 
#     allow_credentials=True,
#     allow_methods=["*"], 
#     allow_headers=["*"],
# )

# security = HTTPBearer()

# # --- PYDANTIC MODELS ---
# class AuthUser(BaseModel):
#     email: str
#     password: str

# class PaymentRecord(BaseModel):
#     loan_id: str
#     amount: float
#     notes: str = "Payment"

# class PaymentRequestCreate(BaseModel):
#     loan_id: str
#     amount: float
#     receipt_url: str

# # --- HELPER: BULLETPROOF ID EXTRACTOR ---
# def get_uid(user) -> str:
#     return str(user.id if hasattr(user, 'id') else user.get('id'))

# # --- SECURITY DEPENDENCIES ---
# def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
#     try:
#         token = credentials.credentials
#         res = supabase.auth.get_user(token)
#         user = res.user if hasattr(res, "user") else res
#         if not user:
#             raise HTTPException(status_code=401, detail="Invalid token")
#         return user
#     except Exception as e:
#         if isinstance(e, HTTPException): raise e
#         raise HTTPException(status_code=401, detail=f"Auth error: {str(e)}")

# # --- LAZY EVALUATION ENGINE ---
# def sync_loan_interest(loan_id: str):
#     response = supabase.table("loans").select("*").eq("id", loan_id).execute()
#     if not response.data: raise HTTPException(status_code=404, detail="Loan not found")
        
#     loan = response.data[0]
#     last_accrual = datetime.fromisoformat(loan["last_accrual_date"].replace('Z', '+00:00'))
#     now = datetime.now(timezone.utc)
    
#     delta = relativedelta(now, last_accrual)
#     months_passed = delta.years * 12 + delta.months
    
#     if months_passed > 0:
#         current_balance = float(loan["current_balance"])
#         rate = float(loan["monthly_interest_rate"])
        
#         for i in range(1, months_passed + 1):
#             interest_amount = current_balance * (rate / 100)
#             current_balance += interest_amount
#             accrual_timestamp = last_accrual + relativedelta(months=i)
            
#             txn_data = {
#                 "loan_id": loan_id,
#                 "amount": round(interest_amount, 2),
#                 "transaction_type": "interest_added",
#                 "description": f"Auto-compounded interest for month {i}",
#                 "created_at": accrual_timestamp.isoformat()
#             }
#             supabase.table("transactions").insert(txn_data).execute()
        
#         new_accrual_date = last_accrual + relativedelta(months=months_passed)
#         supabase.table("loans").update({
#             "current_balance": round(current_balance, 2),
#             "last_accrual_date": new_accrual_date.isoformat()
#         }).eq("id", loan_id).execute()
        
#         return round(current_balance, 2), loan
#     return float(loan["current_balance"]), loan

# # --- APIS ---
# @app.get("/")
# def serve_frontend():
#     return FileResponse("static/index.html")

# @app.get("/config")
# def get_config():
#     """Gives the frontend the Supabase URL so it can upload images directly"""
#     return {"supabase_url": SUPABASE_URL}

# @app.post("/auth/login")
# def login(user: AuthUser):
#     try:
#         res = supabase.auth.sign_in_with_password({"email": user.email, "password": user.password})
#         return {"access_token": res.session.access_token, "user_id": res.user.id}
#     except Exception as e:
#         raise HTTPException(status_code=401, detail=str(e))

# @app.get("/loans/me")
# def get_my_loan(current_user = Depends(get_current_user)):
#     uid = get_uid(current_user)
#     response = supabase.table("loans").select("*").execute()
    
#     my_loan_id = None
#     for loan in response.data:
#         if str(loan["lender_id"]) == uid or str(loan["borrower_id"]) == uid:
#             my_loan_id = loan["id"]
#             break
            
#     if not my_loan_id: raise HTTPException(status_code=404, detail="No loan found")
#     new_balance, loan_data = sync_loan_interest(my_loan_id)
#     return loan_data

# # --- NEW: WORKFLOW APIS ---

# @app.post("/loans/payment-requests")
# def submit_payment_request(req: PaymentRequestCreate, current_user = Depends(get_current_user)):
#     """Borrower submits a payment proof"""
#     uid = get_uid(current_user)
#     data = {
#         "loan_id": req.loan_id,
#         "borrower_id": uid,
#         "amount": req.amount,
#         "receipt_url": req.receipt_url,
#         "status": "pending"
#     }
#     supabase.table("payment_requests").insert(data).execute()
#     return {"message": "Payment request submitted. Waiting for Lender approval."}

# @app.get("/loans/{loan_id}/payment-requests")
# def get_payment_requests(loan_id: str, current_user = Depends(get_current_user)):
#     """Fetch pending and historical requests"""
#     res = supabase.table("payment_requests").select("*").eq("loan_id", loan_id).order("created_at", desc=True).execute()
#     return res.data

# @app.post("/loans/payment-requests/{request_id}/approve")
# def approve_payment(request_id: str, current_user = Depends(get_current_user)):
#     """Lender approves the payment: Updates balance, logs transaction, updates status"""
#     uid = get_uid(current_user)
    
#     # 1. Fetch the request
#     req_res = supabase.table("payment_requests").select("*").eq("id", request_id).execute()
#     if not req_res.data: raise HTTPException(status_code=404, detail="Request not found")
#     request_data = req_res.data[0]
    
#     if request_data["status"] != "pending":
#         raise HTTPException(status_code=400, detail="Request is already processed")

#     # 2. Sync interest and verify Lender
#     current_balance, loan_data = sync_loan_interest(request_data["loan_id"])
#     if uid != str(loan_data["lender_id"]):
#         raise HTTPException(status_code=403, detail="Unauthorized: Only Kishan can approve.")
    
#     # 3. Deduct from balance
#     new_balance = current_balance - request_data["amount"]
#     supabase.table("loans").update({"current_balance": new_balance}).eq("id", request_data["loan_id"]).execute()
    
#     # 4. Log in Ledger
#     txn_data = {
#         "loan_id": request_data["loan_id"],
#         "amount": request_data["amount"],
#         "transaction_type": "payment",
#         "description": "Approved Payment Request"
#     }
#     supabase.table("transactions").insert(txn_data).execute()
    
#     # 5. Mark request as approved
#     supabase.table("payment_requests").update({"status": "approved"}).eq("id", request_id).execute()
#     return {"message": "Payment Approved and Applied to Ledger"}

# @app.post("/loans/payment-requests/{request_id}/reject")
# def reject_payment(request_id: str, current_user = Depends(get_current_user)):
#     """Lender rejects the fake/incorrect payment"""
#     uid = get_uid(current_user)
#     req_res = supabase.table("payment_requests").select("loan_id").eq("id", request_id).execute()
    
#     if req_res.data:
#         _, loan_data = sync_loan_interest(req_res.data[0]["loan_id"])
#         if uid != str(loan_data["lender_id"]):
#             raise HTTPException(status_code=403, detail="Unauthorized")
            
#     supabase.table("payment_requests").update({"status": "rejected"}).eq("id", request_id).execute()
#     return {"message": "Payment Rejected"}

# @app.get("/loans/{loan_id}/transactions")
# def get_transaction_history(loan_id: str, current_user = Depends(get_current_user)):
#     response = supabase.table("transactions").select("*").eq("loan_id", loan_id).order("created_at", desc=True).execute()
#     return response.data

# # --- EASTER EGG API ---

# @app.get("/HowAreYouGoofadKeBacche")
# def goofy_endpoint():
#     """Secret API for testing or just for fun."""
#     return "Hey I am doing good"

# # --- RENDER DEPLOYMENT ENTRY POINT ---
# if __name__ == "__main__":
#     import uvicorn
#     # Render assigns a port dynamically. Default to 8000 for local testing.
#     port = int(os.environ.get("PORT", 8000))
#     # Host must be "0.0.0.0" to allow external connections on Render
#     uvicorn.run("main:app", host="0.0.0.0", port=port)


import os
import resend
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Resend Configuration
resend.api_key = os.getenv("RESEND_API_KEY")
BORROWER_EMAIL = os.getenv("BORROWER_EMAIL")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "onboarding@resend.dev")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- BACKGROUND EMAIL SCHEDULER ---
def check_and_send_due_emails():
    """Runs daily to check loan dates and send Resend emails based on due dates."""
    try:
        # Fetch active loans with a balance greater than 0
        response = supabase.table("loans").select("*").gt("current_balance", 0).execute()
        if not response.data:
            return

        now = datetime.now(timezone.utc)
        
        for loan in response.data:
            # Calculate next due date based on the last accrual date
            last_accrual = datetime.fromisoformat(loan["last_accrual_date"].replace('Z', '+00:00'))
            next_due_date = last_accrual + relativedelta(months=1)
            
            # Days difference (Positive = upcoming, 0 = today, Negative = overdue)
            days_until_due = (next_due_date.date() - now.date()).days
            
            balance = float(loan["current_balance"])
            rate = float(loan["monthly_interest_rate"])
            estimated_interest = balance * (rate / 100)
            
            subject = None
            html_content = None
            
            # 1. Alert 3 days before due date
            if days_until_due == 3:
                subject = "Reminder: Loan Payment Due in 3 Days"
                html_content = f"""
                <h3>Payment Reminder</h3>
                <p>Hi,</p>
                <p>Your loan payment cycle updates in 3 days ({next_due_date.strftime('%b %d, %Y')}).</p>
                <p><strong>Current Balance Due:</strong> ₹{balance:.2f}</p>
                <p><strong>Upcoming Interest to be added:</strong> ₹{estimated_interest:.2f}</p>
                """
            
            # 2. Alert exactly on the due date
            elif days_until_due == 0:
                subject = "Alert: Loan Payment Due Today"
                html_content = f"""
                <h3>Payment Due Today</h3>
                <p>Hi,</p>
                <p>Your loan payment cycle resets TODAY.</p>
                <p><strong>Current Balance Due:</strong> ₹{balance:.2f}</p>
                <p><strong>Interest being added today:</strong> ₹{estimated_interest:.2f}</p>
                """
                
            # 3. Alert every week (7 days) if it's overdue
            elif days_until_due < 0 and abs(days_until_due) % 7 == 0:
                subject = f"Urgent: Loan Payment Overdue by {abs(days_until_due)} Days"
                html_content = f"""
                <h3 style="color: red;">Overdue Payment Alert</h3>
                <p>Hi,</p>
                <p>Your loan balance is currently overdue. Please submit a payment request to clear your dues.</p>
                <p><strong>Current Balance Due:</strong> ₹{balance:.2f}</p>
                """
                
            # Send Email if a condition was met and the borrower email is configured
            if subject and BORROWER_EMAIL:
                params = {
                    "from": SENDER_EMAIL,
                    "to": [BORROWER_EMAIL],
                    "subject": subject,
                    "html": html_content,
                }
                resend.Emails.send(params)
                print(f"[{datetime.now().isoformat()}] Sent '{subject}' to {BORROWER_EMAIL}")

    except Exception as e:
        print(f"Error in check_and_send_due_emails: {str(e)}")


# --- FASTAPI LIFESPAN (Starts Scheduler) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    # Runs every day at 02:30 UTC, which is exactly 08:00 AM IST (Indian Standard Time)
    scheduler.add_job(check_and_send_due_emails, 'cron', hour=2, minute=30)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="Crystal Ledger API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

security = HTTPBearer()

# --- PYDANTIC MODELS ---
class AuthUser(BaseModel):
    email: str
    password: str

class PaymentRecord(BaseModel):
    loan_id: str
    amount: float
    notes: str = "Payment"

class PaymentRequestCreate(BaseModel):
    loan_id: str
    amount: float
    receipt_url: str

# --- HELPER: BULLETPROOF ID EXTRACTOR ---
def get_uid(user) -> str:
    return str(user.id if hasattr(user, 'id') else user.get('id'))

# --- SECURITY DEPENDENCIES ---
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        res = supabase.auth.get_user(token)
        user = res.user if hasattr(res, "user") else res
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=401, detail=f"Auth error: {str(e)}")

# --- LAZY EVALUATION ENGINE ---
def sync_loan_interest(loan_id: str):
    response = supabase.table("loans").select("*").eq("id", loan_id).execute()
    if not response.data: raise HTTPException(status_code=404, detail="Loan not found")
        
    loan = response.data[0]
    last_accrual = datetime.fromisoformat(loan["last_accrual_date"].replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    
    delta = relativedelta(now, last_accrual)
    months_passed = delta.years * 12 + delta.months
    
    if months_passed > 0:
        current_balance = float(loan["current_balance"])
        rate = float(loan["monthly_interest_rate"])
        
        for i in range(1, months_passed + 1):
            interest_amount = current_balance * (rate / 100)
            current_balance += interest_amount
            accrual_timestamp = last_accrual + relativedelta(months=i)
            
            txn_data = {
                "loan_id": loan_id,
                "amount": round(interest_amount, 2),
                "transaction_type": "interest_added",
                "description": f"Auto-compounded interest for month {i}",
                "created_at": accrual_timestamp.isoformat()
            }
            supabase.table("transactions").insert(txn_data).execute()
        
        new_accrual_date = last_accrual + relativedelta(months=months_passed)
        supabase.table("loans").update({
            "current_balance": round(current_balance, 2),
            "last_accrual_date": new_accrual_date.isoformat()
        }).eq("id", loan_id).execute()
        
        return round(current_balance, 2), loan
    return float(loan["current_balance"]), loan

# --- APIS ---
@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")

@app.get("/config")
def get_config():
    """Gives the frontend the Supabase URL so it can upload images directly"""
    return {"supabase_url": SUPABASE_URL}

@app.post("/auth/login")
def login(user: AuthUser):
    try:
        res = supabase.auth.sign_in_with_password({"email": user.email, "password": user.password})
        return {"access_token": res.session.access_token, "user_id": res.user.id}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.get("/loans/me")
def get_my_loan(current_user = Depends(get_current_user)):
    uid = get_uid(current_user)
    
    # IMPROVEMENT: Filter directly in the database instead of downloading all loans
    response = supabase.table("loans").select("*").or_(f"lender_id.eq.{uid},borrower_id.eq.{uid}").execute()
    
    if not response.data: 
        raise HTTPException(status_code=404, detail="No loan found")
        
    my_loan_id = response.data[0]["id"]
    new_balance, loan_data = sync_loan_interest(my_loan_id)
    return loan_data

# --- WORKFLOW APIS ---

@app.post("/loans/payment-requests")
def submit_payment_request(req: PaymentRequestCreate, current_user = Depends(get_current_user)):
    """Borrower submits a payment proof"""
    uid = get_uid(current_user)
    data = {
        "loan_id": req.loan_id,
        "borrower_id": uid,
        "amount": req.amount,
        "receipt_url": req.receipt_url,
        "status": "pending"
    }
    supabase.table("payment_requests").insert(data).execute()
    return {"message": "Payment request submitted. Waiting for Lender approval."}

@app.get("/loans/{loan_id}/payment-requests")
def get_payment_requests(loan_id: str, current_user = Depends(get_current_user)):
    """Fetch pending and historical requests"""
    res = supabase.table("payment_requests").select("*").eq("loan_id", loan_id).order("created_at", desc=True).execute()
    return res.data

@app.post("/loans/payment-requests/{request_id}/approve")
def approve_payment(request_id: str, current_user = Depends(get_current_user)):
    """Lender approves the payment: Updates balance, logs transaction, updates status"""
    uid = get_uid(current_user)
    
    # 1. Fetch the request
    req_res = supabase.table("payment_requests").select("*").eq("id", request_id).execute()
    if not req_res.data: raise HTTPException(status_code=404, detail="Request not found")
    request_data = req_res.data[0]
    
    if request_data["status"] != "pending":
        raise HTTPException(status_code=400, detail="Request is already processed")

    # 2. Sync interest and verify Lender
    current_balance, loan_data = sync_loan_interest(request_data["loan_id"])
    if uid != str(loan_data["lender_id"]):
        raise HTTPException(status_code=403, detail="Unauthorized: Only Kishan can approve.")
    
    # 3. Deduct from balance
    new_balance = current_balance - request_data["amount"]
    supabase.table("loans").update({"current_balance": new_balance}).eq("id", request_data["loan_id"]).execute()
    
    # 4. Log in Ledger
    txn_data = {
        "loan_id": request_data["loan_id"],
        "amount": request_data["amount"],
        "transaction_type": "payment",
        "description": "Approved Payment Request"
    }
    supabase.table("transactions").insert(txn_data).execute()
    
    # 5. Mark request as approved
    supabase.table("payment_requests").update({"status": "approved"}).eq("id", request_id).execute()
    return {"message": "Payment Approved and Applied to Ledger"}

@app.post("/loans/payment-requests/{request_id}/reject")
def reject_payment(request_id: str, current_user = Depends(get_current_user)):
    """Lender rejects the fake/incorrect payment"""
    uid = get_uid(current_user)
    req_res = supabase.table("payment_requests").select("loan_id").eq("id", request_id).execute()
    
    if req_res.data:
        _, loan_data = sync_loan_interest(req_res.data[0]["loan_id"])
        if uid != str(loan_data["lender_id"]):
            raise HTTPException(status_code=403, detail="Unauthorized")
            
    supabase.table("payment_requests").update({"status": "rejected"}).eq("id", request_id).execute()
    return {"message": "Payment Rejected"}

@app.get("/loans/{loan_id}/transactions")
def get_transaction_history(loan_id: str, current_user = Depends(get_current_user)):
    response = supabase.table("transactions").select("*").eq("loan_id", loan_id).order("created_at", desc=True).execute()
    return response.data

# --- EASTER EGG API ---

@app.get("/HowAreYouGoofadKeBacche")
def goofy_endpoint():
    """Secret API for testing or just for fun."""
    return "Hey I am doing good"

# --- RENDER DEPLOYMENT ENTRY POINT ---
if __name__ == "__main__":
    import uvicorn
    # Render assigns a port dynamically. Default to 8000 for local testing.
    port = int(os.environ.get("PORT", 8000))
    # Host must be "0.0.0.0" to allow external connections on Render
    uvicorn.run("main:app", host="0.0.0.0", port=port)
