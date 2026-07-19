import asyncio
import json
import logging
import os
import shutil
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import (
    DOWNLOAD_DIR,
    RATE_LIMIT_INFO,
    RATE_LIMIT_DOWNLOAD,
    FILE_LIFETIME_SECONDS,
    CLEANUP_INTERVAL_SECONDS
)
from app import schemas
from app import downloader

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("yt_downloader")

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="YouTube Downloader API",
    description="A lightweight and Render-optimized API to fetch and download YouTube formats.",
    version="1.0.0"
)

# Attach rate limiter to app state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Start periodic file cleanup task
    asyncio.create_task(cleanup_orphaned_files_loop())
    logger.info("Application startup: registered clean up background loop.")

async def cleanup_orphaned_files_loop():
    """Periodically sweeps the download directory and task registry to free space."""
    while True:
        try:
            logger.info("Running periodic cleanup sweep...")
            now = time.time()
            
            # Clean tasks database and their files
            expired_tasks = []
            for task_id, task in list(downloader.tasks.items()):
                # Delete tasks older than the lifetime limit
                created_at = task.get("created_at", now)
                if now - created_at > FILE_LIFETIME_SECONDS:
                    expired_tasks.append(task_id)
            
            for task_id in expired_tasks:
                task = downloader.tasks.get(task_id)
                if task:
                    filepath = task.get("filepath")
                    if filepath:
                        path = Path(filepath)
                        if path.exists():
                            try:
                                path.unlink()
                                logger.info(f"Cleanup: Removed expired file: {path.name}")
                            except Exception as e:
                                logger.error(f"Cleanup: Error deleting file {filepath}: {e}")
                    # Delete task from dict
                    if task_id in downloader.tasks:
                        del downloader.tasks[task_id]
            
            # Sweep download directory for any unmapped files
            for file in DOWNLOAD_DIR.glob("*"):
                if file.is_file():
                    # If file has been there longer than the lifetime, delete it
                    if now - file.stat().st_mtime > FILE_LIFETIME_SECONDS:
                        try:
                            file.unlink()
                            logger.info(f"Cleanup: Removed unmapped file: {file.name}")
                        except Exception as e:
                            logger.error(f"Cleanup: Error deleting unmapped file {file.name}: {e}")
                            
        except Exception as e:
            logger.error(f"Error in cleanup loop: {e}")
            
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)

def remove_download_file(filepath: str, task_id: str):
    """Background task to remove the file and clean registry entry after download completes."""
    try:
        path = Path(filepath)
        if path.exists():
            path.unlink()
            logger.info(f"Cleaned up file after download: {filepath}")
        if task_id in downloader.tasks:
            del downloader.tasks[task_id]
    except Exception as e:
        logger.error(f"Error cleaning up download {filepath} after server response: {e}")

# API Routes
@app.get("/")
def read_root():
    """Root endpoint for Render default deployment checks."""
    return {"status": "healthy", "message": "YouTube Downloader API is running"}

@app.get("/api/health")
def health_check():
    """Checks the API health and FFmpeg availability."""
    ffmpeg_available = shutil.which("ffmpeg") is not None
    import yt_dlp
    return {
        "status": "healthy",
        "ffmpeg": ffmpeg_available,
        "yt_dlp_version": yt_dlp.version.__version__
    }

@app.get("/api/cookies-debug")
def cookies_debug():
    """Diagnostic endpoint to inspect cookies files in the container."""
    import os
    from app.config import COOKIES_FILE
    
    files_in_app = os.listdir("/app") if os.path.exists("/app") else []
    
    cookie_file_status = {}
    cookie_paths = [
        "/app/cookies.txt", 
        "/app/www.youtube.com_cookies.txt", 
        "./cookies.txt", 
        "./www.youtube.com_cookies.txt"
    ]
    for cp in cookie_paths:
        p = Path(cp)
        exists = p.exists()
        is_file = p.is_file() if exists else False
        size = p.stat().st_size if exists else 0
        first_line = ""
        if exists and is_file:
            try:
                with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                    first_line = f.readline()
            except Exception as e:
                first_line = f"Error: {e}"
        cookie_file_status[cp] = {
            "exists": exists,
            "is_file": is_file,
            "size": size,
            "first_line": first_line
        }
        
    return {
        "configured_cookies_file": str(COOKIES_FILE) if COOKIES_FILE else None,
        "files_in_app": files_in_app,
        "cookie_file_status": cookie_file_status,
        "env_cookies_file": os.getenv("COOKIES_FILE")
    }

@app.post("/api/info", response_model=schemas.InfoResponse)
@limiter.limit(RATE_LIMIT_INFO)
def get_info(request: Request, body: schemas.InfoRequest):
    """Extracts metadata and available formats (up to 720p) for a YouTube URL."""
    try:
        logger.info(f"Metadata query requested for URL: {body.url}")
        info = downloader.extract_video_info(body.url)
        return info
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/download", response_model=schemas.DownloadResponse)
@limiter.limit(RATE_LIMIT_DOWNLOAD)
def request_download(request: Request, body: schemas.DownloadRequest):
    """Initiates the download for the given URL and quality format."""
    # First, get title to name the output file later
    try:
        info = downloader.extract_video_info(body.url)
        title = info.get("title", "download")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to resolve URL metadata: {str(e)}")

    try:
        task_id = downloader.start_download(body.url, body.format_id, title)
        # Update creation timestamp for the task
        if task_id in downloader.tasks:
            downloader.tasks[task_id]["created_at"] = time.time()
        logger.info(f"Initiated download task {task_id} for format {body.format_id}")
        return schemas.DownloadResponse(task_id=task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download/progress/{task_id}")
def get_download_progress(task_id: str):
    """Server-Sent Events endpoint returning the real-time download status of a task."""
    
    async def sse_event_generator():
        # Check initially if task exists
        if task_id not in downloader.tasks:
            yield f"data: {json.dumps({'status': 'error', 'error': 'Task not found'})}\n\n"
            return

        while True:
            task = downloader.tasks.get(task_id)
            if not task:
                break
            
            yield f"data: {json.dumps(task)}\n\n"
            
            # If the download completed or hit an error, exit the SSE stream
            if task.get("status") in ["completed", "error"]:
                break
                
            await asyncio.sleep(1.0)

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")

@app.get("/api/download/file/{task_id}")
def download_file(task_id: str, background_tasks: BackgroundTasks):
    """Serves the completed download file to the client and schedules its deletion."""
    task = downloader.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or expired")
        
    if task.get("status") != "completed":
        raise HTTPException(status_code=400, detail=f"File not ready. Status: {task.get('status')}")
        
    filepath = task.get("filepath")
    filename = task.get("filename", f"download-{task_id}.mp4")
    
    if not filepath or not Path(filepath).exists():
        raise HTTPException(status_code=404, detail="The file was not found on the server.")
        
    # Queue removal of the file and task registry metadata after serving it
    background_tasks.add_task(remove_download_file, filepath, task_id)
    
    # URL-encode the filename for Content-Disposition (RFC 5987 compliance)
    encoded_filename = quote(filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
    }
    
    # Determine the correct media type from file extension
    ext = Path(filepath).suffix.lower()
    if ext == ".mp4":
        media_type = "video/mp4"
    elif ext == ".mp3":
        media_type = "audio/mpeg"
    elif ext == ".m4a":
        media_type = "audio/mp4"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        path=filepath,
        media_type=media_type,
        filename=filename,
        headers=headers
    )
