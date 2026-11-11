# BioQuote Agent
AI agent that quotes, bills (PayPal sandbox) and delivers small bioinformatics jobs. MIT licensed.
Public/synthetic data only.

## Run
    python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    cp .env.example .env   # fill PayPal sandbox keys + LLM endpoint (Ollama by default)
    uvicorn app.main:app --reload

## Free stack
Ollama or Groq free tier (LLM, optional - templates used if unavailable), PayPal sandbox, FastAPI,
AG Grid Community, Render free tier. Dashboard + chat at `/`. Webhook: `POST /webhooks/paypal`.
Local test without PayPal: set `ALLOW_DEV_PAY=1`, then `POST /api/dev/pay/{job_id}`.
