# web/app.py
import os, sys, json, traceback, tempfile
from typing import Optional
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, Response

# include project root so your modules import without restructuring
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from .bridge import run as run_business

app = FastAPI(title="YourApp Web")

@app.get("/favicon.ico")
def favicon():
    # avoid 404 noise
    return Response(content=b"", media_type="image/x-icon", status_code=200)

# minimal inline HTML (ASCII only) so no templates folder is needed
HTML_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>YourApp</title></head>
<body>
<form id="f" method="post" enctype="multipart/form-data" action="/api/run">
<input name="text" placeholder="text">
<input name="file" type="file">
<button type="submit">send</button>
</form>
<pre id="out"></pre>
<script>
const f=document.getElementById('f');const out=document.getElementById('out');
f.addEventListener('submit',async(e)=>{e.preventDefault();const fd=new FormData(f);
const r=await fetch('/api/run',{method:'POST',body:fd});out.textContent=await r.text();});
</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PAGE

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/api/run")
async def api_run(text: str = Form(None), file: Optional[UploadFile] = File(None)):
    try:
        file_path = None
        if file is not None:
            td = tempfile.mkdtemp()
            file_path = os.path.join(td, file.filename or "upload.bin")
            with open(file_path, "wb") as f:
                f.write(await file.read())

        result = run_business({"text": text or "", "file_path": file_path})
        try:
            json.dumps(result)  # ensure JSON-serializable
        except Exception:
            result = {"result": str(result)}
        return JSONResponse(result)
    except Exception:
        return JSONResponse(
            {"error": "internal error", "trace": traceback.format_exc()},
            status_code=500,
        )
