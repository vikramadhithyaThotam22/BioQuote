import os
from dotenv import load_dotenv
load_dotenv()
import json, threading
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from . import agent, db, paypal, runner, seed

app = FastAPI(title="BioQuote Agent")

@app.on_event("startup")
def _startup(): seed.seed_demo_jobs()

_lock = threading.Lock()
def on_payment_confirmed(job_id: str):
    """Idempotent: first confirmation (webhook OR capture) starts the pipeline once."""
    with _lock:
        job = db.get_job(job_id)
        if not job or job["status"] not in ("quoted", "awaiting_payment"): return
        db.update_job(job_id, status="paid")
    threading.Thread(target=runner.run_job, args=(db.get_job(job_id),), daemon=True).start()

SESSIONS: dict[str, list] = {}

@app.get("/health")
def health(): return {"ok": True}

@app.post("/api/chat")
async def api_chat(payload: dict):
    sid = payload.get("session_id", "default")
    hist = SESSIONS.setdefault(sid, [])
    hist.append({"role": "user", "content": payload["message"]})
    ctx = {"file_path": payload.get("file_path")}
    try:
        reply, SESSIONS[sid] = agent.chat(hist, ctx)
    except Exception as e:
        import logging; logging.getLogger('uvicorn.error').error('LLM call failed: %r', e)
        hist.pop()   # drop the unanswered user turn so the session stays valid
        raise HTTPException(503, "The AI model is busy or rate-limited (free tier). Please try again in a minute.")
    return {"reply": reply, "job_id": ctx.get("job_id")}

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    os.makedirs("uploads", exist_ok=True)
    path = os.path.join("uploads", os.path.basename(file.filename))
    data = await file.read()
    open(path, "wb").write(data)
    return {"file_path": path, "size_mb": round(len(data) / 1e6, 3)}

@app.get("/api/jobs")
def jobs(): return db.list_jobs()

# --- manual PayPal endpoints (also useful for testing without the LLM) ---
@app.post("/api/orders")
def make_order(payload: dict):
    job = db.get_job(payload["job_id"])
    if not job: raise HTTPException(404, "job not found")
    base = os.getenv("APP_BASE_URL", "http://localhost:8000")
    o = paypal.create_order(job["id"], job["amount_usd"], job["request"],
                            f"{base}/paypal/return?job_id={job['id']}", f"{base}/paypal/cancel?job_id={job['id']}")
    db.update_job(job["id"], paypal_order_id=o["order_id"], approve_url=o["approve_url"], status="awaiting_payment")
    return o

@app.get("/paypal/return", response_class=HTMLResponse)
def paypal_return(job_id: str, token: str):
    """Buyer approved -> capture. (Nov 10: the webhook will be the source of truth that triggers the pipeline.)"""
    cap = paypal.capture_order(token)
    if cap.get("status") == "COMPLETED":
        on_payment_confirmed(job_id)
    return f"<h2>Payment {cap.get('status')}</h2><p>Job {job_id}. <a href='/'>Back to dashboard</a></p>"

@app.get("/paypal/cancel", response_class=HTMLResponse)
def paypal_cancel(job_id: str):
    return f"<h2>Payment cancelled</h2><p>Job {job_id}.</p>"


@app.post("/webhooks/paypal")
async def paypal_webhook(request: Request):
    raw = await request.body()
    event = json.loads(raw)
    headers = {k.lower(): v for k, v in request.headers.items()}
    if os.getenv("PAYPAL_WEBHOOK_ID"):
        if not paypal.verify_webhook(headers, event): raise HTTPException(400, "bad signature")
    elif os.getenv("ALLOW_UNVERIFIED_WEBHOOKS") != "1":
        raise HTTPException(400, "PAYPAL_WEBHOOK_ID not set")
    if event.get("event_type") == "PAYMENT.CAPTURE.COMPLETED":
        res = event["resource"]
        job_id = res.get("custom_id")
        if not job_id:
            oid = res.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
            j = db.get_job_by_order(oid) if oid else None
            job_id = j["id"] if j else None
        if job_id: on_payment_confirmed(job_id)
    return {"ok": True}

@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str):
    j = db.get_job(job_id)
    if not j: raise HTTPException(404)
    j["result"] = json.loads(j["result_json"]) if j.get("result_json") else None
    return j

@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str):
    j = db.get_job(job_id)
    r = json.loads(j["result_json"]) if j and j.get("result_json") else {}
    if not r.get("file") or not os.path.exists(r["file"]): raise HTTPException(404, "no result yet")
    return FileResponse(r["file"], filename=os.path.basename(r["file"]))

@app.post("/api/dev/pay/{job_id}")
def dev_pay(job_id: str):
    """Local testing only: simulate a confirmed payment (disabled unless ALLOW_DEV_PAY=1)."""
    if os.getenv("ALLOW_DEV_PAY") != "1": raise HTTPException(403)
    on_payment_confirmed(job_id); return {"ok": True}

app.mount("/", StaticFiles(directory="static", html=True), name="static")
