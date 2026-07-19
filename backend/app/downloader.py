import asyncio
import logging
import re
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
import yt_dlp

from app.config import DOWNLOAD_DIR, COOKIES_FILE, MAX_FILE_SIZE_BYTES

logger = logging.getLogger(__name__)

# Global in-memory task database
# Maps task_id -> task_metadata dict
tasks: Dict[str, Dict[str, Any]] = {}

# Utility functions for formatting
def format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "Unknown"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def format_size(bytes_val: Optional[int]) -> str:
    if not bytes_val:
        return "Unknown size"
    val = float(bytes_val)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if val < 1024:
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{val:.1f} TB"

def format_speed(bytes_per_sec: Optional[float]) -> str:
    if not bytes_per_sec:
        return "0 KB/s"
    val = float(bytes_per_sec)
    for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
        if val < 1024:
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{val:.1f} TB/s"

def format_eta(seconds: Optional[int]) -> str:
    if seconds is None:
        return "Unknown"
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes}m {remaining_seconds}s"

def clean_url(url: str) -> str:
    # Basic URL cleaning to remove spaces or unwanted wrapper characters
    return url.strip()

def is_valid_url(url: str) -> bool:
    # Match standard web URLs
    url_pattern = re.compile(
        r'^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)\/.*$',
        re.IGNORECASE
    )
    return bool(url_pattern.match(url))

def get_youtube_dl_opts(extra_opts: Optional[dict] = None) -> dict:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'no_color': True,
        'ignoreconfig': True, # Ignore local/system config files
    }
    if COOKIES_FILE and COOKIES_FILE.exists():
        opts['cookiefile'] = str(COOKIES_FILE)
        logger.info(f"Using cookies from: {COOKIES_FILE}")
    if extra_opts:
        opts.update(extra_opts)
    return opts

def extract_video_info(url: str) -> dict:
    url = clean_url(url)
    if not is_valid_url(url):
        raise ValueError("Invalid YouTube URL. Please provide a valid YouTube link.")

    ydl_opts = get_youtube_dl_opts({'skip_download': True})
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            logger.error(f"Error extracting video info: {e}")
            raise RuntimeError(f"Could not extract video metadata: {str(e)}")
        
        # Check playlist
        if 'entries' in info:
            # It's a playlist. For a simple app, we take the first video or raise a message.
            # Let's take the first entry if it exists.
            entries = list(info['entries'])
            if not entries:
                raise ValueError("The provided playlist is empty.")
            info = entries[0]
            logger.info("Playlist detected. Processing the first video in the playlist.")

        # Extract size estimates for common targets: 720p, 480p, 360p, mp3, m4a
        formats = info.get('formats', [])
        
        # Find best audio formats
        best_audio = None
        best_m4a_audio = None
        for f in formats:
            if f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                # It is audio
                if not best_audio or f.get('tbr', 0) > best_audio.get('tbr', 0):
                    best_audio = f
                if f.get('ext') == 'm4a':
                    if not best_m4a_audio or f.get('tbr', 0) > best_m4a_audio.get('tbr', 0):
                        best_m4a_audio = f

        audio_size = best_audio.get('filesize') or best_audio.get('filesize_approx') or 0 if best_audio else 0
        m4a_size = best_m4a_audio.get('filesize') or best_m4a_audio.get('filesize_approx') or 0 if best_m4a_audio else 0

        # Let's build our format options
        options = []
        
        # Resolutions we want to support (capped at 720p for Render compatibility)
        resolutions = [720, 480, 360]
        
        for res in resolutions:
            # Find the best MP4 video format of this resolution
            best_video_of_res = None
            # 1. Prioritize H.264 (avc) for Apple/QuickTime compatibility
            for f in formats:
                vcodec = f.get('vcodec') or ''
                if (f.get('height') == res and 
                    vcodec != 'none' and 
                    (vcodec.startswith('avc1') or 'avc' in vcodec)):
                    if not best_video_of_res or f.get('tbr', 0) > best_video_of_res.get('tbr', 0):
                        best_video_of_res = f
            
            # 2. Fall back to any MP4 video
            if not best_video_of_res:
                for f in formats:
                    if (f.get('height') == res and 
                        f.get('vcodec') != 'none' and 
                        f.get('ext') == 'mp4'):
                        if not best_video_of_res or f.get('tbr', 0) > best_video_of_res.get('tbr', 0):
                            best_video_of_res = f
            
            # 3. Fall back to any video format of this height
            if not best_video_of_res:
                for f in formats:
                    if f.get('height') == res and f.get('vcodec') != 'none':
                        if not best_video_of_res or f.get('tbr', 0) > best_video_of_res.get('tbr', 0):
                            best_video_of_res = f

            if best_video_of_res:
                v_size = best_video_of_res.get('filesize') or best_video_of_res.get('filesize_approx') or 0
                # Combine size of video and audio if it is video-only (requires merge)
                total_size = v_size + audio_size if best_video_of_res.get('acodec') == 'none' else v_size
                
                # Check against size limits
                if MAX_FILE_SIZE_BYTES and total_size > MAX_FILE_SIZE_BYTES:
                    logger.warning(f"Skipping {res}p format because estimated size {total_size} exceeds limit.")
                    continue

                options.append({
                    "id": f"{res}p",
                    "label": f"{res}p MP4",
                    "size": format_size(total_size) if total_size > 0 else "Unknown size",
                    "type": "video",
                    "ext": "mp4"
                })

        # Add Audio options
        if best_audio:
            # MP3
            # Check size limits
            if not MAX_FILE_SIZE_BYTES or audio_size <= MAX_FILE_SIZE_BYTES:
                options.append({
                    "id": "mp3",
                    "label": "MP3 Audio (Highest Quality)",
                    "size": format_size(audio_size) if audio_size > 0 else "Unknown size",
                    "type": "audio",
                    "ext": "mp3"
                })
        
        if best_m4a_audio:
            if not MAX_FILE_SIZE_BYTES or m4a_size <= MAX_FILE_SIZE_BYTES:
                options.append({
                    "id": "m4a",
                    "label": "M4A Audio",
                    "size": format_size(m4a_size) if m4a_size > 0 else "Unknown size",
                    "type": "audio",
                    "ext": "m4a"
                })

        return {
            "title": info.get('title', 'Unknown Video'),
            "channel": info.get('uploader', 'Unknown Channel'),
            "duration": format_duration(info.get('duration')),
            "thumbnail": info.get('thumbnail'),
            "formats": options
        }

def make_progress_hook(task_id: str):
    def hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes') or 0
            
            # Prevent size limit violation during active download
            if MAX_FILE_SIZE_BYTES and downloaded > MAX_FILE_SIZE_BYTES:
                raise ValueError(f"Download aborted: Size exceeds maximum limit of {format_size(MAX_FILE_SIZE_BYTES)}")

            progress = (downloaded / total * 100) if total > 0 else 0
            
            speed_val = d.get('speed')
            speed = format_speed(speed_val) if speed_val else "0 KB/s"
            
            eta_val = d.get('eta')
            eta = format_eta(eta_val) if eta_val else "Unknown"

            tasks[task_id].update({
                "status": "downloading",
                "progress": round(progress, 1),
                "speed": speed,
                "eta": eta
            })
            
        elif d['status'] == 'finished':
            tasks[task_id].update({
                "status": "processing",
                "progress": 100.0,
                "speed": "0 KB/s",
                "eta": "0s"
            })
    return hook

def run_download_thread(task_id: str, url: str, format_id: str, title: str):
    tasks[task_id] = {
        "status": "queued",
        "progress": 0.0,
        "speed": "0 KB/s",
        "eta": "Waiting",
        "filename": None,
        "filepath": None,
        "error": None,
        "title": title
    }

    try:
        # Define downloading format and postprocessing rules
        # Map our friendly format IDs to yt-dlp format strings
        if format_id == "720p":
            ydl_format = 'bestvideo[vcodec^=avc1][height<=720]+bestaudio[acodec^=mp4a]/best[ext=mp4][vcodec^=avc1][height<=720]/best[height<=720]'
            postprocessors = []
            out_ext = "mp4"
        elif format_id == "480p":
            ydl_format = 'bestvideo[vcodec^=avc1][height<=480]+bestaudio[acodec^=mp4a]/best[ext=mp4][vcodec^=avc1][height<=480]/best[height<=480]'
            postprocessors = []
            out_ext = "mp4"
        elif format_id == "360p":
            ydl_format = 'bestvideo[vcodec^=avc1][height<=360]+bestaudio[acodec^=mp4a]/best[ext=mp4][vcodec^=avc1][height<=360]/best[height<=360]'
            postprocessors = []
            out_ext = "mp4"
        elif format_id == "mp3":
            ydl_format = 'bestaudio[ext=m4a]/bestaudio'
            postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
            out_ext = "mp3"
        elif format_id == "m4a":
            ydl_format = 'bestaudio[ext=m4a]/bestaudio'
            postprocessors = []
            out_ext = "m4a"
        else:
            raise ValueError(f"Unsupported format selection: {format_id}")

        # Secure output template: use the task UUID to avoid conflicts and shell injections
        outtmpl = str(DOWNLOAD_DIR / f"{task_id}.%(ext)s")

        extra_opts = {
            'format': ydl_format,
            'outtmpl': outtmpl,
            'progress_hooks': [make_progress_hook(task_id)],
            'postprocessors': postprocessors,
            # Render Optimization: constraint download buffers to minimize RAM footprint
            'buffersize': 1024 * 16, # 16KB buffers
            'http_chunk_size': 1024 * 1024, # 1MB chunks to avoid memory accumulation
        }
        if format_id in ["720p", "480p", "360p"]:
            extra_opts['merge_output_format'] = 'mp4'

        ydl_opts = get_youtube_dl_opts(extra_opts)

        logger.info(f"Starting yt-dlp download for task {task_id} with format {format_id}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Search for the final downloaded file with the correct extension
        # Since postprocessing (like MP3 conversion) changes the final extension, we look up task_id.*
        final_file = None
        for path in DOWNLOAD_DIR.glob(f"{task_id}.*"):
            if path.suffix not in ['.part', '.ytdl']:
                final_file = path
                break
        
        if not final_file or not final_file.exists():
            raise FileNotFoundError("Downloaded output file could not be found.")

        # Clean title for clean filename delivery
        # Strip illegal characters for file systems
        clean_title = re.sub(r'[\\/*?:"<>|]', "", title)
        # Ensure correct extension
        ext = final_file.suffix.lstrip(".")
        filename = f"{clean_title}.{ext}"

        tasks[task_id].update({
            "status": "completed",
            "progress": 100.0,
            "filename": filename,
            "filepath": str(final_file)
        })
        logger.info(f"Download complete for task {task_id}: {filename}")

    except Exception as e:
        logger.exception(f"Error processing download in thread for task {task_id}: {e}")
        tasks[task_id].update({
            "status": "error",
            "error": str(e)
        })

def start_download(url: str, format_id: str, title: str) -> str:
    import uuid
    task_id = str(uuid.uuid4())
    
    # Run the downloader in a separate background thread to keep FastAPI completely responsive
    thread = threading.Thread(
        target=run_download_thread,
        args=(task_id, url, format_id, title),
        daemon=True
    )
    thread.start()
    return task_id

def find_task_file(task_id: str) -> Optional[Path]:
    task = tasks.get(task_id)
    if task and task.get("filepath"):
        path = Path(task["filepath"])
        if path.exists():
            return path
    return None
