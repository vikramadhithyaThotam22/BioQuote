"""Seed demo rows so the dashboard is never empty (Render free tier resets SQLite)."""
import json, time
from . import db

def seed_demo_jobs():
    if db.list_jobs(): return
    demos = [("Annotate 200-variant demo VCF, summarize pathogenic", "vcf_annotation", 13.5, "completed"),
             ("Quick VCF summary for student project", "vcf_summary", 10.0, "paid"),
             ("RNA-seq QC for 6 samples", "rnaseq_qc", 25.0, "awaiting_payment"),
             ("Summarize trio VCF", "vcf_summary", 12.25, "quoted")]
    for i, (req, jt, amt, st) in enumerate(demos):
        jid = db.create_job(req, jt, {"total_usd": amt}, amt)
        fields = {"status": st, "created": time.time() - 3600 * (i + 1) * 5}
        if st == "completed":
            fields["result_json"] = json.dumps({"report": "Demo report: 200 variants, 2 flagged Pathogenic/Likely pathogenic.", "file": ""})
        db.update_job(jid, **fields)
