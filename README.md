# YTDownloader - Simple & Beautiful YouTube Downloader Web App

YTDownloader is a lightweight, mobile-friendly web application designed to let you download YouTube videos (up to 720p) and audio files (MP3/M4A) directly on your phone or computer.

Optimized to run stably on **Render's Free Tier (512 MB RAM limit)**, it limits resource intensive merging and re-encoding, ensuring smooth and fast operations.

---

## Features
- **Modern Responsive Design**: Premium dark-mode interface with glassmorphic cards and glowing background orbs, optimized for mobile screens.
- **Render-Optimized**: Caps resolution options at 720p to avoid out-of-memory crashes on cheap/free hosting plans.
- **Real-Time Progress Tracking**: Uses Server-Sent Events (SSE) to stream download percentage, download speed, and ETA directly to the UI.
- **Automatic Cleanup**: Instantly deletes downloads from the disk after they are sent to the client, plus runs a background thread every 10 minutes to clean orphaned files.
- **Security Protections**: Safe YouTube URL regex validation, IP rate limiting, and zero direct shell execution (prevents command injection).
- **Split Hosting Support**: Allows you to point the frontend to any external API base URL directly from the interface, making free deployment on Static Site providers possible.
- **Age-Restriction Bypass**: Supports mounting a `cookies.txt` file to bypass YouTube's age verification or download private videos you have access to.

---

## Tech Stack
- **Backend**: Python + FastAPI
- **Downloader**: `yt-dlp` (via its official Python API library)
- **Frontend**: HTML5 + Vanilla CSS3 (Glassmorphic variables design) + JavaScript
- **Video Processing**: FFmpeg
- **Reverse Proxy**: Nginx (configured to support unbuffered SSE streams)
- **Deployment**: Docker & Docker Compose

---

## Local Setup

### Option 1: Docker Compose (Recommended)
This mirrors production and mounts Nginx to reverse proxy the app on port `8080`.

1. Ensure you have Docker and Docker Compose installed.
2. In the project root, start the container stack:
   ```bash
   docker-compose up --build -d
   ```
3. Open your browser and navigate to `http://localhost:8080`.

### Option 2: Manual Run (No Docker)
You can run the backend and frontend separately on your local machine.

#### 1. Start the Backend:
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. Open the Frontend:
Because our frontend JavaScript (`frontend/app.js`) is smart, you can simply double-click and open `frontend/index.html` directly in your browser. It will automatically detect that you're running locally and route its API requests to the running backend at `http://localhost:8000`.

---

## Render Deployment Guide (100% Free)

You can host this entire stack on Render for free using their Web Service (for Python) and Static Site (for HTML/CSS/JS) tiers.

### Step 1: Deploy the FastAPI Backend (Web Service)
1. Push this project folder to your GitHub.
2. Log into [Render](https://render.com/) and click **New +** -> **Web Service**.
3. Connect your GitHub repository.
4. Configure the service:
   - **Name**: `ytdl-api` (or any name)
   - **Runtime**: `Docker`
   - **Build Context**: `backend`
   - **Dockerfile Path**: `backend/Dockerfile`
   - **Instance Type**: `Free`
5. Add the following **Environment Variables** in the Advanced section:
   - `DOWNLOAD_DIR` = `/tmp/yt-downloads`
   - `MAX_FILE_SIZE_MB` = `500`
   - `RATE_LIMIT_INFO` = `10/minute`
   - `RATE_LIMIT_DOWNLOAD` = `3/minute`
   - `FILE_LIFETIME_SECONDS` = `3600`
6. Click **Create Web Service**. Wait for it to build. Once deployed, copy your backend URL (e.g., `https://ytdl-api.onrender.com`).

### Step 2: Deploy the Frontend (Static Site)
1. On the Render Dashboard, click **New +** -> **Static Site**.
2. Connect the same GitHub repository.
3. Configure the static site:
   - **Name**: `ytdl-app` (or any name)
   - **Build Command**: *(Leave empty)*
   - **Publish Directory**: `frontend`
4. Click **Create Static Site**.
5. Once deployed, open your frontend site URL (e.g., `https://ytdl-app.onrender.com`).

### Step 3: Link Frontend to Backend
1. Open your deployed Static Site URL in your mobile browser or computer.
2. Click the **Profile/User Badge icon** (top-right corner of the interface).
3. In the popup prompt, paste your **Render Backend Web Service URL** (e.g., `https://ytdl-api.onrender.com`) and click OK.
4. The page will reload. Your app is now connected and ready to download!

---

## How to bypass age restrictions (Cookies)

If you get errors downloading age-restricted videos:
1. Install a browser extension like **Get cookies.txt LOCALLY** (Chrome/Firefox).
2. Log into YouTube, click the extension, and export your cookies in **Netscape format**.
3. Save the exported text file as `cookies.txt` in the root of the project directory.
4. **Docker setup**: The `docker-compose.yml` mounts this automatically to the backend.
5. **Render setup**: You can paste the contents of `cookies.txt` into Render as a Secret File mounted at `/app/cookies.txt`.
