"""Lightweight Windows dev proxy that emulates the LiteLLM proxy on port 4000.
Bypasses the uvloop build failure on Windows and forwards `reasoner`/`fast` requests
to OpenRouter or the configured OpenAI-compatible endpoint.
"""

from __future__ import annotations

import os
from pathlib import Path
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="ClearTrade LiteLLM Dev Proxy")

# Load .env
env_path = Path(__file__).resolve().parent.parent / ".env"
OPENROUTER_KEY = ""
MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k == "OPENAI_API_KEYS":
                OPENROUTER_KEY = v.split(",")[0].strip()
            elif k in ("LLM_REASONER_MODEL", "LLM_FAST_MODEL") and v:
                # Strip prefix like openrouter/
                clean_model = v.replace("openrouter/", "")
                if clean_model:
                    MODEL = clean_model

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

@app.get("/health")
def health():
    return {"status": "healthy", "mode": "windows-dev-proxy"}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model_req = body.get("model", "fast")
    
    # Map reasoner/fast to actual OpenRouter model with fallbacks
    body["model"] = MODEL
    body["models"] = [
        MODEL,
        "liquid/lfm-2.5-2.6b:free",
        "xingchen-agi/xing4.0-29b-a4b:free",
    ]
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://cleartrade.local",
        "X-Title": "ClearTrade Trade Finance Engine",
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(OPENROUTER_URL, json=body, headers=headers)
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type="application/json",
            )
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={"error": {"message": f"Dev proxy upstream error: {e}"}},
            )

if __name__ == "__main__":
    print(f"Starting LiteLLM Dev Proxy on http://127.0.0.1:4000 -> {MODEL}")
    uvicorn.run(app, host="127.0.0.1", port=4000, log_level="warning")
