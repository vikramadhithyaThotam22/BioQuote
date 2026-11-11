"""Lightweight VCF summary + ClinVar-style flagging + report (LLM with free template fallback)."""
import csv, gzip, json, os
from collections import Counter
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
CLINVAR = ROOT / "samples" / "clinvar_mini.tsv"
DEMO_VCF = ROOT / "samples" / "demo.vcf"
RESULTS = ROOT / "results"
TRANSITIONS = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}
FLAG = {"Pathogenic", "Likely_pathogenic"}

def _load_clinvar():
    db = {}
    for line in open(CLINVAR):
        if line.startswith("#") or line.startswith("chrom"): continue
        c, p, r, a, g, sig, cond = line.rstrip("\n").split("\t")
        db[(c, p, r, a)] = (g, sig, cond)
    return db

def parse_vcf(path):
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt") as f:
        for line in f:
            if line.startswith("#") or not line.strip(): continue
            x = line.rstrip("\n").split("\t")
            if len(x) < 5: continue
            for alt in x[4].split(","):
                yield x[0].removeprefix("chr"), x[1], x[3], alt, x[5] if len(x) > 5 else ".", x[6] if len(x) > 6 else "."

def analyze(vcf_path, job_id):
    cv = _load_clinvar()
    n = ti = tv = 0
    types, chroms, flagged, annotated = Counter(), Counter(), [], []
    for c, p, r, a, qual, filt in parse_vcf(vcf_path):
        n += 1; chroms[c] += 1
        if len(r) == 1 and len(a) == 1:
            types["SNV"] += 1
            if (r, a) in TRANSITIONS: ti += 1
            else: tv += 1
        elif len(r) < len(a): types["insertion"] += 1
        elif len(r) > len(a): types["deletion"] += 1
        else: types["MNV/other"] += 1
        hit = cv.get((c, p, r, a))
        row = {"chrom": c, "pos": p, "ref": r, "alt": a, "qual": qual, "filter": filt,
               "gene": hit[0] if hit else "", "clinvar": hit[1] if hit else "", "condition": hit[2] if hit else ""}
        annotated.append(row)
        if hit and hit[1] in FLAG: flagged.append(row)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{job_id}_annotated.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(annotated[0]) if annotated else ["chrom"])
        w.writeheader(); w.writerows(annotated)
    summary = {"total_variants": n, "variant_types": dict(types), "ti_tv": round(ti / tv, 2) if tv else None,
               "top_chromosomes": dict(chroms.most_common(5)), "flagged_pathogenic": flagged,
               "annotated_with_clinvar": sum(1 for r in annotated if r["clinvar"])}
    return summary, str(out)

def template_report(s):
    fl = s["flagged_pathogenic"]
    lines = [f"Your file contains {s['total_variants']} variants "
             f"({', '.join(f'{v} {k}' for k, v in s['variant_types'].items())}).",
             f"Transition/transversion ratio: {s['ti_tv']}." if s["ti_tv"] else "",
             f"{s['annotated_with_clinvar']} variants matched our ClinVar-style reference table."]
    if fl:
        lines.append(f"{len(fl)} variant(s) are flagged Pathogenic/Likely pathogenic: " +
                     "; ".join(f"{v['gene']} chr{v['chrom']}:{v['pos']} {v['ref']}>{v['alt']} ({v['clinvar']})" for v in fl) + ".")
    else:
        lines.append("No pathogenic or likely pathogenic variants were flagged.")
    lines.append("This is an automated research summary, not a clinical diagnosis. Consult a clinical geneticist.")
    return "\n".join(l for l in lines if l)

def write_report(s):
    base = os.getenv("LLM_BASE_URL")
    if not base: return template_report(s)
    try:
        r = httpx.post(f"{base.rstrip('/')}/chat/completions", timeout=25,
            headers={"Authorization": f"Bearer {os.getenv('LLM_API_KEY', 'none')}"},
            json={"model": os.getenv("LLM_MODEL", "llama3.1"), "temperature": 0.2, "messages": [
                {"role": "system", "content": "You write short plain-English summaries of VCF results for non-bioinformaticians. "
                 "Use ONLY the numbers given. End with a reminder this is not a clinical diagnosis."},
                {"role": "user", "content": json.dumps(s)}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip() or template_report(s)
    except Exception:
        return template_report(s)   # free fallback: never block delivery

def run_job(job):
    from . import db
    db.update_job(job["id"], status="running")
    try:
        path = job.get("file_path")
        if not path and job["job_type"] in ("vcf_annotation", "vcf_summary"):
            path = str(DEMO_VCF)          # demo mode: no upload -> use synthetic sample
        if not path:
            raise ValueError("No input file was uploaded; this job type needs manual handling.")
        if not (path.endswith(".vcf") or path.endswith(".vcf.gz")):
            raise ValueError("Only VCF jobs are automated in this demo; this one needs manual handling.")
        summary, out = analyze(path, job["id"])
        db.update_job(job["id"], status="completed",
                      result_json=json.dumps({"summary": summary, "report": write_report(summary), "file": out}))
    except Exception as e:
        db.update_job(job["id"], status="failed", result_json=json.dumps({"error": str(e)}))
