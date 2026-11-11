import os
os.environ["LLM_BASE_URL"] = "http://127.0.0.1:9/v1"      # unreachable -> forces the fallback
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app import db

def test_fallback_quote_accept_status():
    with TestClient(app) as c, patch("app.paypal.create_order", return_value={"order_id": "O1", "status": "CREATED", "approve_url": "https://sandbox.paypal.test/pay"}):
        r = c.post("/api/chat", json={"session_id": "fb", "message": "Annotate my 2 MB VCF and summarize pathogenic variants"}).json()
        assert "Total: $21.00" in r["reply"] and r["job_id"]
        r2 = c.post("/api/chat", json={"session_id": "fb", "message": "Yes, I accept"}).json()
        assert "https://sandbox.paypal.test/pay" in r2["reply"]
        r3 = c.post("/api/chat", json={"session_id": "fb", "message": "have I paid yet?"}).json()
        assert "awaiting payment" in r3["reply"]
        assert db.get_job(r["job_id"])["paypal_order_id"] == "O1"

def test_fallback_refuses_phi_and_offtopic():
    with TestClient(app) as c:
        assert "synthetic" in c.post("/api/chat", json={"session_id": "p", "message": "annotate my real patient John Doe VCF"}).json()["reply"]
        assert "bioinformatics" in c.post("/api/chat", json={"session_id": "o", "message": "capital of France?"}).json()["reply"]
