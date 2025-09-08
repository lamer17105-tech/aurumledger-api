# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>Aurum Web OK</h1><p>主程式載入成功。</p>"

# 讓「python main.py」也能跑（選擇性）
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
