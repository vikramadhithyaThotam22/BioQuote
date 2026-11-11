"""Deterministic pricing so the LLM never invents numbers."""
RATES = {  # base USD, per-MB USD
    "vcf_annotation": (15.0, 0.50),
    "vcf_summary": (8.0, 0.25),
    "rnaseq_qc": (20.0, 0.10),
    "other": (25.0, 0.50),
}
REPORT_FEE = 5.0
MIN_TOTAL = 10.0

def build_quote(job_type: str, size_mb: float, rush: bool = False) -> dict:
    base, per_mb = RATES.get(job_type, RATES["other"])
    items = [{"item": f"{job_type} base", "usd": base},
             {"item": f"Data processing ({size_mb:.2f} MB)", "usd": round(size_mb * per_mb, 2)},
             {"item": "AI plain-English report", "usd": REPORT_FEE}]
    if rush:
        items.append({"item": "Rush (+25%)", "usd": round(0.25 * sum(i["usd"] for i in items), 2)})
    total = max(MIN_TOTAL, round(sum(i["usd"] for i in items), 2))
    est_minutes = round(2 + size_mb * 0.5, 1)
    return {"job_type": job_type, "line_items": items, "total_usd": total, "est_minutes": est_minutes}
