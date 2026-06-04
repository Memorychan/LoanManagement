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
# app = FastAPI(title="Loan Tracker API - Kishan & Karan")

# # --- CORS SETUP ---
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

# class LoanCreate(BaseModel):
#     borrower_id: str
#     initial_principal: float = 1000000.0
#     monthly_interest_rate: float = 3.0

# # --- HELPER: BULLETPROOF ID EXTRACTOR ---
# def get_uid(user) -> str:
#     """Safely extracts the User ID regardless of the Supabase SDK version"""
#     return str(user.id if hasattr(user, 'id') else user.get('id'))

# # --- SECURITY DEPENDENCIES ---
# def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
#     """Verifies the JWT token and returns the user object from Supabase."""
#     try:
#         token = credentials.credentials
#         res = supabase.auth.get_user(token)
        
#         user = res.user if hasattr(res, "user") else res
#         if not user:
#             raise HTTPException(status_code=401, detail="Invalid token")
#         return user
#     except Exception as e:
#         # X-RAY VISION: Show the actual error (e.g. JWT Expired) instead of a generic message
#         if isinstance(e, HTTPException):
#             raise e
#         raise HTTPException(status_code=401, detail=f"Auth error: {str(e)}")

# # --- LAZY EVALUATION ENGINE ---
# def sync_loan_interest(loan_id: str):
#     """Calculates missing months of compound interest on the fly."""
#     response = supabase.table("loans").select("*").eq("id", loan_id).execute()
#     if not response.data:
#         raise HTTPException(status_code=404, detail="Loan not found")
        
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


# # --- FRONTEND ROUTE ---
# @app.get("/")
# def serve_frontend():
#     return FileResponse("static/index.html")

# # --- AUTHENTICATION APIS ---
# @app.post("/auth/login")
# def login(user: AuthUser):
#     try:
#         res = supabase.auth.sign_in_with_password({"email": user.email, "password": user.password})
#         return {"access_token": res.session.access_token, "user_id": res.user.id}
#     except Exception as e:
#         # X-RAY VISION: Show the actual error (e.g. Invalid credentials)
#         raise HTTPException(status_code=401, detail=str(e))

# # --- PROTECTED LOAN APIS ---
# @app.get("/loans/me")
# def get_my_loan(current_user = Depends(get_current_user)):
#     """Automatically finds the loan associated with the logged-in user"""
#     uid = get_uid(current_user)
    
#     response = supabase.table("loans").select("*").execute()
    
#     my_loan_id = None
#     for loan in response.data:
#         if str(loan["lender_id"]) == uid or str(loan["borrower_id"]) == uid:
#             my_loan_id = loan["id"]
#             break
            
#     if not my_loan_id:
#         raise HTTPException(status_code=404, detail=f"No loan found in database for User ID: {uid}")
        
#     new_balance, loan_data = sync_loan_interest(my_loan_id)
#     return loan_data

# @app.post("/loans/record-payment")
# def record_payment(payment: PaymentRecord, current_user = Depends(get_current_user)):
#     uid = get_uid(current_user)
#     current_balance, loan_data = sync_loan_interest(payment.loan_id)
    
#     if uid != str(loan_data["lender_id"]):
#         raise HTTPException(status_code=403, detail="Unauthorized: Only Kishan can record payments.")
    
#     new_balance = current_balance - payment.amount
#     supabase.table("loans").update({"current_balance": new_balance}).eq("id", payment.loan_id).execute()
    
#     txn_data = {
#         "loan_id": payment.loan_id,
#         "amount": payment.amount,
#         "transaction_type": "payment",
#         "description": payment.notes
#     }
#     supabase.table("transactions").insert(txn_data).execute()
    
#     return {"message": "Payment recorded successfully", "new_balance": new_balance}

# @app.get("/loans/{loan_id}/transactions")
# def get_transaction_history(loan_id: str, current_user = Depends(get_current_user)):
#     uid = get_uid(current_user)
#     _, loan_data = sync_loan_interest(loan_id)
    
#     if uid not in [str(loan_data["lender_id"]), str(loan_data["borrower_id"])]:
#         raise HTTPException(status_code=403, detail="Unauthorized to view this ledger.")
        
#     response = supabase.table("transactions").select("*").eq("loan_id", loan_id).order("created_at", desc=True).execute()
#     return response.data

import os
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
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

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI(title="Crystal Ledger API")

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
    response = supabase.table("loans").select("*").execute()
    
    my_loan_id = None
    for loan in response.data:
        if str(loan["lender_id"]) == uid or str(loan["borrower_id"]) == uid:
            my_loan_id = loan["id"]
            break
            
    if not my_loan_id: raise HTTPException(status_code=404, detail="No loan found")
    new_balance, loan_data = sync_loan_interest(my_loan_id)
    return loan_data

# --- NEW: WORKFLOW APIS ---

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