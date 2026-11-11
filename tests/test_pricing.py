from app.pricing import build_quote
def test_quote_total():
    q = build_quote("vcf_summary", 2.0)
    assert q["total_usd"] == 13.5
def test_minimum():
    assert build_quote("vcf_summary", 0.0)["total_usd"] == 13.0
def test_rush_more():
    assert build_quote("vcf_annotation", 1, True)["total_usd"] > build_quote("vcf_annotation", 1)["total_usd"]
