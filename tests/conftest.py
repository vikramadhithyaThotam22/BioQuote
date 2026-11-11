import os, tempfile
# Keep tests off the real database (must be set before app.db is imported).
os.environ["BIOQUOTE_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
