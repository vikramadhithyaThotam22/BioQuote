import os, time, json
os.environ.update(ALLOW_UNVERIFIED_WEBHOOKS="1", ALLOW_DEV_PAY="1")
os.environ.pop("PAYPAL_WEBHOOK_ID", None); os.environ["LLM_BASE_URL"] = ""
from fastapi.testclient import TestClient
from app.main import app
from app import db, runner

def test_runner_flags():
    s, out = runner.analyze(runner.DEMO_VCF, "t")
    assert s["total_variants"] == 200 and len(s["flagged_pathogenic"]) == 3
    assert "flagged" in runner.template_report(s) or "Pathogenic" in runner.template_report(s)

def test_webhook_triggers_pipeline():
    jid = db.create_job("t", "vcf_summary", {}, 10.0); db.update_job(jid, status="awaiting_payment")
    with TestClient(app) as c:
        r = c.post("/webhooks/paypal", json={"event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"custom_id": jid}})
        assert r.status_code == 200
        for _ in range(50):
            if db.get_job(jid)["status"] == "completed": break
            time.sleep(0.1)
        assert db.get_job(jid)["status"] == "completed"
        assert c.get(f"/api/jobs/{jid}/result").status_code == 200
        assert c.get("/").status_code == 200

def test_rnaseq_without_file_fails_cleanly():
    jid = db.create_job("rna", "rnaseq_qc", {}, 20.0)
    runner.run_job(db.get_job(jid))
    assert db.get_job(jid)["status"] == "failed"
