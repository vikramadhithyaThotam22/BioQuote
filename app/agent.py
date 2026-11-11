"""LLM tool-calling agent (any OpenAI-compatible endpoint, e.g. Ollama/Groq/OpenRouter): request -> quote -> PayPal order -> payment check."""
import json, os, time
import httpx
from . import db, paypal, pricing

MODEL = lambda: os.getenv("LLM_MODEL", "llama3.1")
LLM_URL = lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
BASE_URL = lambda: os.getenv("APP_BASE_URL", "http://localhost:8000")

SYSTEM = """You are BioQuote Agent, a friendly assistant that quotes and sells small bioinformatics jobs
(VCF annotation/summary, RNA-seq QC) to small labs, students and clinics. Flow: understand the request,
call create_quote (never invent prices), show the itemized quote, and ONLY after the user agrees call
create_paypal_order and give them the approval link. Use check_payment when they say they've paid.
Jobs run automatically after payment is confirmed. Only public/synthetic data is supported - refuse real
patient identifiable data. Rules: ONE user request = ONE job = ONE create_quote call (pick the single best job_type; annotation includes
the summary of pathogenic variants). Create ONE PayPal order per job_id, only once. Politely decline anything
unrelated to bioinformatics jobs, quotes or payments (no general chat, trivia or advice). If the user gives no file size, assume a typical size (VCF ~1 MB, RNA-seq QC ~50 MB) and say so; never assume
more than 100 MB. Keep replies short. Use simple bullet lists, never tables."""

_RAW_TOOLS = [
 {"name": "create_quote", "description": "Create an itemized quote for a job. Returns job_id and total.",
  "input_schema": {"type": "object", "properties": {
     "job_type": {"type": "string", "enum": ["vcf_annotation", "vcf_summary", "rnaseq_qc", "other"]},
     "size_mb": {"type": "number", "description": "Input size in MB (use the uploaded file size if given; else estimate)"},
     "rush": {"type": "boolean"},
     "summary": {"type": "string", "description": "One-line job description"}},
   "required": ["job_type", "size_mb", "summary"]}},
 {"name": "create_paypal_order", "description": "Create a PayPal sandbox order for an accepted quote.",
  "input_schema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
 {"name": "check_payment", "description": "Check payment/job status for a job.",
  "input_schema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
]

TOOLS = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
          "parameters": t["input_schema"]}} for t in _RAW_TOOLS]

def run_tool(name: str, args: dict, ctx: dict) -> dict:
    if name == "create_quote":
        q = pricing.build_quote(args["job_type"], float(args["size_mb"]), bool(args.get("rush")))
        jid = db.create_job(args["summary"], args["job_type"], q, q["total_usd"], ctx.get("file_path"))
        ctx["job_id"] = jid
        return {"job_id": jid, **q}
    if name == "create_paypal_order":
        job = db.get_job(args["job_id"])
        if not job: return {"error": "unknown job_id"}
        o = paypal.create_order(job["id"], job["amount_usd"], job["request"],
                                f"{BASE_URL()}/paypal/return?job_id={job['id']}",
                                f"{BASE_URL()}/paypal/cancel?job_id={job['id']}")
        db.update_job(job["id"], paypal_order_id=o["order_id"], approve_url=o["approve_url"], status="awaiting_payment")
        return {"job_id": job["id"], **o}
    if name == "check_payment":
        job = db.get_job(args["job_id"])
        if not job: return {"error": "unknown job_id"}
        return {"job_id": job["id"], "status": job["status"], "amount_usd": job["amount_usd"]}
    return {"error": f"unknown tool {name}"}

def chat(messages: list, ctx: dict | None = None, max_turns: int = 6) -> tuple[str, list]:
    """Run the tool loop. `messages` is OpenAI-format history (no system msg); returns (reply, history)."""
    ctx = ctx if ctx is not None else {}
    headers = {"Authorization": f"Bearer {os.getenv('LLM_API_KEY', 'none')}"}
    for _ in range(max_turns):
        for attempt in range(5):   # free tiers return 429/503 under load
            r = httpx.post(f"{LLM_URL()}/chat/completions", headers=headers, timeout=120, json={
                "model": MODEL(), "tools": TOOLS, "temperature": 0.2,
                "messages": [{"role": "system", "content": SYSTEM}, *messages]})
            if r.status_code not in (429, 500, 503): break
            time.sleep(min(float(r.headers.get('retry-after', 2 ** attempt)), 20))
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        messages.append({k: v for k, v in msg.items() if v is not None})
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content") or "", messages
        for c in calls:
            try:
                out = run_tool(c["function"]["name"], json.loads(c["function"]["arguments"] or "{}"), ctx)
            except Exception as e:
                out = {"error": str(e)}
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(out)})
    return "Sorry, I couldn't finish that - please try again.", messages
