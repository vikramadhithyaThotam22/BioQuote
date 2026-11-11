from fastapi.testclient import TestClient
from app.main import app
from app import db, runner
import json

def test_pdf_report():
    jid = db.create_job("Annotate demo VCF", "vcf_annotation", {}, 20.5)
    s, out = runner.analyze(runner.DEMO_VCF, jid)
    db.update_job(jid, status="completed", result_json=json.dumps({"summary": s, "report": "**Hello** report\n- point one", "file": out}))
    with TestClient(app) as c:
        r = c.get(f"/api/jobs/{jid}/report.pdf")
        assert r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 2000
        assert c.get("/api/jobs/nope/report.pdf").status_code == 404
