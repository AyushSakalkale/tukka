// Resolve API Base URL depending on development vs production Docker setup
const getApiBaseUrl = () => {
    // If a custom API base is set in localStorage (e.g., override configuration)
    const customBase = localStorage.getItem('API_BASE_URL');
    if (customBase) {
        return customBase;
    }
    
    // If running locally on your Mac
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        if (window.location.port === '8080' || window.location.port === '80' || window.location.port === '') {
            // Local Docker Compose / Nginx reverse proxy
            return '';
        }
        // Local direct FastAPI backend running on port 8000
        return 'http://localhost:8000';
    }

    // Default production backend hosted on Render
    return 'https://tukka.onrender.com';
};

const API_BASE = getApiBaseUrl();

// DOM Elements
const urlInput = document.getElementById('url-input');
const pasteBtn = document.getElementById('paste-btn');
const parseBtn = document.getElementById('parse-btn');
const parseSpinner = document.getElementById('parse-spinner');
const errorBox = document.getElementById('error-box');
const errorMessage = document.getElementById('error-message');
const metaCard = document.getElementById('meta-card');
const videoThumbnail = document.getElementById('video-thumbnail');
const videoDuration = document.getElementById('video-duration');
const videoTitle = document.getElementById('video-title');
const videoChannel = document.getElementById('video-channel');
const formatsSection = document.getElementById('formats-section');
const formatsContainer = document.getElementById('formats-container');
const progressCard = document.getElementById('download-progress-card');
const progressLabel = document.getElementById('downloading-format-label');
const progressPercent = document.getElementById('download-percentage');
const progressBarFill = document.getElementById('progress-bar-fill');
const downloadSpeed = document.getElementById('download-speed');
const downloadEta = document.getElementById('download-eta');
const downloadStatus = document.getElementById('download-status');
const successBox = document.getElementById('success-box');
const mainCard = document.querySelector('.main-card');
const userBadge = document.querySelector('.user-badge');

// App state
let currentVideoInfo = null;
let currentUrl = "";
let eventSource = null;

// Helpers
function showNotice(box, textElement, msg, duration = 0) {
    textElement.textContent = msg;
    box.classList.remove('hidden');
    if (duration > 0) {
        setTimeout(() => box.classList.add('hidden'), duration);
    }
}

function clearNotices() {
    errorBox.classList.add('hidden');
    successBox.classList.add('hidden');
}

function setParsingState(isParsing) {
    if (isParsing) {
        parseSpinner.classList.remove('hidden');
        parseBtn.disabled = true;
        mainCard.classList.add('working');
        clearNotices();
    } else {
        parseSpinner.classList.add('hidden');
        parseBtn.disabled = false;
        mainCard.classList.remove('working');
    }
}

// Clipboard Paste
pasteBtn.addEventListener('click', async () => {
    try {
        if (!navigator.clipboard || !navigator.clipboard.readText) {
            alert("Clipboard access is not fully supported on this browser. Please paste manually.");
            return;
        }
        const text = await navigator.clipboard.readText();
        if (text) {
            urlInput.value = text.trim();
        }
    } catch (err) {
        console.error('Failed to read clipboard contents: ', err);
        // Fallback or user alert
    }
});

// Custom API Base Configuration (Developer Mode)
userBadge.addEventListener('click', () => {
    const currentBase = localStorage.getItem('API_BASE_URL') || '';
    const newBase = prompt(
        "Configure Backend API URL\n\nLeave empty if backend is behind the Nginx reverse proxy (default).\nFor custom hosting (e.g. Render), paste your backend service URL (e.g. https://ytdl-api.onrender.com):",
        currentBase
    );
    if (newBase !== null) {
        let formattedBase = newBase.trim();
        if (formattedBase && formattedBase.endsWith('/')) {
            formattedBase = formattedBase.slice(0, -1);
        }
        if (formattedBase) {
            localStorage.setItem('API_BASE_URL', formattedBase);
            alert(`Backend API URL updated to: ${formattedBase}`);
        } else {
            localStorage.removeItem('API_BASE_URL');
            alert("Backend API URL reset to default proxy routing.");
        }
        window.location.reload();
    }
});

// URL Parser
parseBtn.addEventListener('click', async () => {
    const url = urlInput.value.trim();
    if (!url) {
        showNotice(errorBox, errorMessage, "Please paste a YouTube URL first.");
        return;
    }

    currentUrl = url;
    setParsingState(true);
    metaCard.classList.add('hidden');
    formatsSection.classList.add('hidden');
    progressCard.classList.add('hidden');

    try {
        const response = await fetch(`${API_BASE}/api/info`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Failed to retrieve video metadata.");
        }

        const data = await response.json();
        currentVideoInfo = data;
        renderMetadata(data);
    } catch (err) {
        showNotice(errorBox, errorMessage, err.message);
        console.error("Parse Error:", err);
    } finally {
        setParsingState(false);
    }
});

// Render metadata & formats
function renderMetadata(data) {
    videoThumbnail.src = data.thumbnail || "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?q=80&w=300&auto=format&fit=crop";
    videoDuration.textContent = data.duration;
    videoTitle.textContent = data.title;
    videoChannel.textContent = data.channel;
    
    metaCard.classList.remove('hidden');

    // Render formats list
    formatsContainer.innerHTML = '';
    
    if (!data.formats || data.formats.length === 0) {
        formatsContainer.innerHTML = '<p class="format-size" style="text-align: center;">No compatible formats found. Please try another link.</p>';
    } else {
        data.formats.forEach(format => {
            const row = document.createElement('div');
            row.className = 'format-item';
            
            // Icon selection depending on video/audio type
            const iconSvg = format.type === 'video' 
                ? `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="17" x2="22" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/></svg>`
                : `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`;

            row.innerHTML = `
                <div class="format-item-left">
                    <div class="format-icon">${iconSvg}</div>
                    <div class="format-info">
                        <span class="format-label">${format.label}</span>
                        <span class="format-size">Size: ${format.size}</span>
                    </div>
                </div>
                <button class="format-btn" onclick="startFormatDownload('${format.id}', '${format.label}')">Download</button>
            `;
            formatsContainer.appendChild(row);
        });
    }

    formatsSection.classList.remove('hidden');
}

// Start format download trigger
window.startFormatDownload = async (formatId, formatLabel) => {
    clearNotices();
    progressCard.classList.add('hidden');
    mainCard.classList.add('working');

    try {
        const response = await fetch(`${API_BASE}/api/download`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: currentUrl,
                format_id: formatId
            })
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Failed to request download.");
        }

        const data = await response.json();
        const taskId = data.task_id;
        
        // Hide format selections to focus on download status
        formatsSection.classList.add('hidden');
        
        // Setup SSE listener for the download progress
        listenToProgress(taskId, formatLabel);

    } catch (err) {
        showNotice(errorBox, errorMessage, err.message);
        mainCard.classList.remove('working');
        formatsSection.classList.remove('hidden');
        console.error("Download start failed:", err);
    }
};

// SSE Progress listener
function listenToProgress(taskId, formatLabel) {
    if (eventSource) {
        eventSource.close();
    }

    progressLabel.textContent = `Downloading ${formatLabel}...`;
    progressBarFill.style.width = '0%';
    progressPercent.textContent = '0%';
    downloadSpeed.textContent = '0 KB/s';
    downloadEta.textContent = 'Estimating...';
    downloadStatus.textContent = 'Queued';
    downloadStatus.className = 'meta-value status-active';
    
    progressCard.classList.remove('hidden');

    eventSource = new EventSource(`${API_BASE}/api/download/progress/${taskId}`);

    eventSource.onmessage = (event) => {
        const task = JSON.parse(event.data);

        if (task.status === 'error') {
            eventSource.close();
            showNotice(errorBox, errorMessage, task.error || "An error occurred during downloading.");
            progressCard.classList.add('hidden');
            formatsSection.classList.remove('hidden');
            mainCard.classList.remove('working');
            return;
        }

        // Update progress bar
        const progress = task.progress || 0;
        progressBarFill.style.width = `${progress}%`;
        progressPercent.textContent = `${progress}%`;

        // Update meta items
        downloadSpeed.textContent = task.speed || '0 KB/s';
        downloadEta.textContent = task.eta || 'Unknown';
        
        if (task.status === 'downloading') {
            downloadStatus.textContent = 'Downloading';
        } else if (task.status === 'processing') {
            downloadStatus.textContent = 'Converting/Merging';
            downloadStatus.className = 'meta-value status-active';
            progressBarFill.style.width = `100%`;
            progressPercent.textContent = `100%`;
        } else if (task.status === 'completed') {
            eventSource.close();
            downloadStatus.textContent = 'Finished';
            downloadStatus.className = 'meta-value';
            
            // Auto download file to phone/client
            triggerFileDownload(taskId);
            
            progressCard.classList.add('hidden');
            showNotice(successBox, successBox.querySelector('p'), "Download finished! Your file download started automatically.", 6000);
            mainCard.classList.remove('working');
            
            // Reset state
            urlInput.value = "";
            metaCard.classList.add('hidden');
        }
    };

    eventSource.onerror = (err) => {
        console.error("SSE EventSource error: ", err);
        eventSource.close();
        showNotice(errorBox, errorMessage, "Lost connection to progress monitor. The server might be processing the file.");
        // Try fallback check or just reset state
        mainCard.classList.remove('working');
        progressCard.classList.add('hidden');
        formatsSection.classList.remove('hidden');
    };
}

// Trigger browser download via dynamic link injection
function triggerFileDownload(taskId) {
    const downloadUrl = `${API_BASE}/api/download/file/${taskId}`;
    
    const link = document.createElement('a');
    link.href = downloadUrl;
    // Let the server headers specify the clean filename, but standard fallback
    link.setAttribute('download', '');
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
