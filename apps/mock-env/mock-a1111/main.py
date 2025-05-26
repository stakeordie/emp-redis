#!/usr/bin/env python3
# [2025-05-26T14:23:00-04:00] Created mock A1111 service for testing
import os
import time
import json
import random
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List, Union

# Create FastAPI app
app = FastAPI(title="Mock A1111 API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# [2025-05-26T14:32:00-04:00] Global variables to track progress
current_progress = 0.0
is_processing = False
job_id = None
job_start_time = None
job_duration = 10.0  # Default job duration in seconds as float

# Model for txt2img request
class Txt2ImgRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = ""
    width: Optional[int] = 512
    height: Optional[int] = 512
    steps: Optional[int] = 20
    cfg_scale: Optional[float] = 7.0
    seed: Optional[int] = -1
    batch_size: Optional[int] = 1
    n_iter: Optional[int] = 1
    sampler_name: Optional[str] = "Euler a"

# Health check endpoint
@app.get("/healthz")
async def health_check():
    return {"status": "ok"}

# Progress endpoint
@app.get("/sdapi/v1/progress")
async def get_progress():
    global current_progress, is_processing, job_id, job_start_time, job_duration
    
    if is_processing and job_start_time is not None:
        elapsed = time.time() - job_start_time
        if elapsed >= job_duration:
            current_progress = 1.0
            is_processing = False
        else:
            current_progress = min(elapsed / job_duration, 0.99)
    
    # [2025-05-26T14:27:00-04:00] Fixed potential None value in calculation
    eta = 0
    if is_processing and job_start_time is not None:
        eta = max(0, job_duration - (time.time() - job_start_time))
    
    return {
        "progress": current_progress,
        "eta_relative": eta,
        "state": {
            "skipped": False,
            "interrupted": False,
            "job": job_id,
            "job_count": 1,
            "job_timestamp": job_start_time,
            "job_no": 0,
            "sampling_step": int(current_progress * 20),
            "sampling_steps": 20
        },
        "current_image": None,
        "textinfo": f"Step {int(current_progress * 20)}/20"
    }

# txt2img endpoint
@app.post("/sdapi/v1/txt2img")
async def txt2img(request: Txt2ImgRequest):
    global current_progress, is_processing, job_id, job_start_time, job_duration
    
    # Start a new job
    job_id = f"mock-job-{int(time.time())}"
    job_start_time = time.time()
    is_processing = True
    current_progress = 0.0
    
    # Set job duration based on steps
    # [2025-05-26T14:27:00-04:00] Fixed type incompatibility
    job_duration = float(request.steps) * 0.5  # 0.5 seconds per step
    
    # Generate mock image data
    return {
        "images": ["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="],
        "parameters": request.dict(),
        "info": json.dumps({
            "prompt": request.prompt,
            "seed": request.seed if request.seed != -1 else random.randint(0, 2**32 - 1),
            "width": request.width,
            "height": request.height,
            "steps": request.steps,
            "cfg_scale": request.cfg_scale,
            "job_id": job_id
        })
    }

# img2img endpoint
@app.post("/sdapi/v1/img2img")
async def img2img(request: Request):
    global current_progress, is_processing, job_id, job_start_time, job_duration
    
    # Parse request body
    body = await request.json()
    
    # Start a new job
    job_id = f"mock-job-{int(time.time())}"
    job_start_time = time.time()
    is_processing = True
    current_progress = 0.0
    
    # Set job duration based on steps
    # [2025-05-26T14:27:00-04:00] Fixed potential None value and type incompatibility
    steps = body.get("steps", 20)
    if steps is None:
        steps = 20
    job_duration = float(steps) * 0.5  # 0.5 seconds per step
    
    # Generate mock image data
    return {
        "images": ["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="],
        "parameters": body,
        "info": json.dumps({
            "prompt": body.get("prompt", ""),
            "seed": body.get("seed", random.randint(0, 2**32 - 1)),
            "width": body.get("width", 512),
            "height": body.get("height", 512),
            "steps": steps,
            "job_id": job_id
        })
    }

# Interrupt endpoint
@app.post("/sdapi/v1/interrupt")
async def interrupt():
    global is_processing
    is_processing = False
    return {"status": "ok"}

# Options endpoint
@app.get("/sdapi/v1/options")
async def get_options():
    return {
        "sd_model_checkpoint": "v1-5-pruned-emaonly.safetensors",
        "sd_vae": "vae-ft-mse-840000-ema-pruned.safetensors",
        "sd_hypernetwork": "None",
        "sd_lora": "None",
        "outdir_txt2img_samples": "outputs/txt2img-images",
        "outdir_img2img_samples": "outputs/img2img-images",
        "outdir_extras_samples": "outputs/extras-images",
        "outdir_save": "log/images",
        "outdir_grids": "outputs/grids"
    }

# Models endpoint
@app.get("/sdapi/v1/sd-models")
async def get_models():
    return [
        {
            "title": "v1-5-pruned-emaonly.safetensors",
            "model_name": "v1-5-pruned-emaonly",
            "hash": "81761151",
            "filename": "v1-5-pruned-emaonly.safetensors",
            "config": "configs/stable-diffusion/v1-inference.yaml"
        },
        {
            "title": "sd-v1-4.ckpt",
            "model_name": "sd-v1-4",
            "hash": "fe4efff1e174c627256e44ec2991ba279b3816e364b49f9be2abc0b3ff3f8556",
            "filename": "models/Stable-diffusion/sd-v1-4.ckpt",
            "config": "configs/stable-diffusion/v1-inference.yaml"
        }
    ]

# Samplers endpoint
@app.get("/sdapi/v1/samplers")
async def get_samplers():
    return [
        {"name": "Euler a", "aliases": ["euler_ancestral", "k_euler_a"], "options": {}},
        {"name": "Euler", "aliases": ["euler", "k_euler"], "options": {}},
        {"name": "DPM++ 2M Karras", "aliases": ["dpm++_2m_karras"], "options": {}}
    ]

# Main entry point
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"[2025-05-26T14:23:00-04:00] Starting mock A1111 API server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
