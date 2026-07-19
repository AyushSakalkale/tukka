import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "/tmp/yt-downloads"))

# Create download directory if it doesn't exist
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Security & Limits
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 500))  # Max 500MB download limit
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Rate Limiting
RATE_LIMIT_INFO = os.getenv("RATE_LIMIT_INFO", "10/minute")
RATE_LIMIT_DOWNLOAD = os.getenv("RATE_LIMIT_DOWNLOAD", "3/minute")

# Cookies for Age-Restricted Content
def is_valid_cookies_file(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            return "# Netscape" in first_line or "HTTP Cookie File" in first_line
    except Exception:
        return False

# Checked in order of preference
cookies_env = os.getenv("COOKIES_FILE")
raw_cookies_file = None

possible_paths = []
if cookies_env:
    possible_paths.append(Path(cookies_env))

# Add workspace root, backend, and app container paths for both file names
possible_paths.extend([
    BASE_DIR.parent / "cookies.txt",
    BASE_DIR.parent / "www.youtube.com_cookies.txt",
    BASE_DIR / "cookies.txt",
    BASE_DIR / "www.youtube.com_cookies.txt",
    Path("/app/cookies.txt"),
    Path("/app/www.youtube.com_cookies.txt")
])

for path in possible_paths:
    if path.exists() and is_valid_cookies_file(path):
        raw_cookies_file = path
        break

if raw_cookies_file:
    COOKIES_FILE = raw_cookies_file
    # Use print for early startup logs so it displays before logging config initializes
    print(f"Loaded valid Netscape cookies from: {COOKIES_FILE}", flush=True)
else:
    COOKIES_FILE = None

# Cleanup settings
FILE_LIFETIME_SECONDS = int(os.getenv("FILE_LIFETIME_SECONDS", 3600))  # 1 hour
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", 600))  # 10 minutes
