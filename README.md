# BioQuote Agent

An AI agent that **quotes, bills and delivers small bioinformatics jobs** through PayPal.

Small labs, students and clinics often need a one-off analysis (variant annotation, a VCF summary) but cannot
afford a full-time bioinformatician, and freelancers lose time on quoting, invoicing and chasing payment.
BioQuote Agent automates that loop: describe the job in chat → get an itemized quote → pay with PayPal →
the pipeline runs automatically → receive a plain-English report and a downloadable result file.

> **Data policy:** use only public or synthetic data. The demo ships a synthetic VCF and a synthetic
> ClinVar-style table. Never upload real patient data.

## How it works

```
Chat UI ──► /api/chat ──► LLM agent (tool calling)
                            ├─ create_quote         deterministic pricing (the LLM never invents prices)
                            ├─ create_paypal_order  PayPal Orders v2 (sandbox)
                            └─ check_payment        job/payment status
Buyer pays ─► PayPal ─► webhook PAYMENT.CAPTURE.COMPLETED ─► /webhooks/paypal (signature verified)
                                         └─► job runner: VCF summary + ClinVar-style flags
                                              └─► AI-written report + annotated CSV
AG Grid dashboard shows jobs, quotes, payments and statuses.
```

- **Agentic commerce:** the agent creates the quote and the PayPal order through tool calls, then checks payment.
- **Idempotent confirmation:** the webhook (source of truth) or the return-URL capture starts the pipeline once.
- **Free-tier friendly:** works with any OpenAI-compatible LLM (Groq, Gemini, Ollama, OpenRouter). If the LLM
  is down or rate-limited, the report falls back to a template so delivery never breaks.

## Stack (all free)
FastAPI · PayPal sandbox (Orders v2 + webhooks) · OpenAI-compatible LLM (default: Groq `openai/gpt-oss-120b`)
· AG Grid Community · SQLite · Render free tier.

## Run locally
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the values below
uvicorn app.main:app --reload
```
Open http://localhost:8000.

### Environment variables
| Variable | Purpose |
|---|---|
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | PayPal **sandbox** app credentials (use a US Business merchant) |
| `PAYPAL_WEBHOOK_ID` | ID of the webhook registered for `PAYMENT.CAPTURE.COMPLETED` |
| `APP_BASE_URL` | Public URL of the app (PayPal return/cancel links) |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | Any OpenAI-compatible endpoint, e.g. `https://api.groq.com/openai/v1` + `openai/gpt-oss-120b` |
| `ALLOW_DEV_PAY=1` | **Local testing only:** enables `POST /api/dev/pay/{job_id}` to simulate payment |

## Try it
1. In the chat, type e.g. *"Annotate my VCF (about 1 MB) and summarize pathogenic variants"*
   (optionally upload `samples/demo.vcf`).
2. Review the quote, reply *"yes"*, and open the PayPal link.
3. Pay with a **sandbox Personal (buyer) account** (create one at developer.paypal.com → Sandbox Accounts;
   a buyer cannot be the same account as the merchant, and both should be in the US so USD works).
4. After payment the job moves `awaiting_payment → paid → running → completed` in the dashboard. Each completed job has a **PDF report** and an annotated **CSV** to download.
   Click the row for the report; download the annotated CSV.

## Deploy on Render
1. New → Blueprint → select this repo (`render.yaml` is included).
2. Set `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `LLM_API_KEY`, and `APP_BASE_URL=https://<name>.onrender.com`.
3. In the PayPal developer dashboard add a webhook `https://<name>.onrender.com/webhooks/paypal` for
   `PAYMENT.CAPTURE.COMPLETED`, copy its ID into `PAYPAL_WEBHOOK_ID`, and redeploy.

The free tier sleeps when idle; open the URL a minute before a demo. SQLite resets on restart, so demo jobs
are re-seeded at startup.

## Tests
```bash
pytest -q
```

## Scope and limitations
Only VCF jobs are automated end to end (summary, variant types, Ti/Tv, ClinVar-style flags). Other job types
are quoted and billed but need manual handling. The reference table is synthetic; outputs are research
summaries, **not clinical diagnoses**.

## How it was built
Built for a hackathon with Claude Code assisting the development. The runtime agent is model-agnostic.

## License
MIT — see [LICENSE](LICENSE).
