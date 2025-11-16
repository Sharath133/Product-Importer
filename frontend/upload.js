let selectedFile = null;
let eventSource = null;

const uploadZone = document.getElementById("upload-zone");
const fileInput = document.getElementById("csv-file-input");
const uploadButton = document.getElementById("upload-button");
const fileInfo = document.getElementById("file-info");
const fileName = document.getElementById("file-name");
const fileSize = document.getElementById("file-size");
const progressContainer = document.getElementById("upload-progress");
const statusLabel = document.getElementById("upload-status");
const percentageLabel = document.getElementById("upload-percentage");
const progressBar = document.getElementById("upload-progress-bar");
const logOutput = document.getElementById("upload-log");
const errorBox = document.getElementById("upload-error");

const API_BASE = "";

export function initializeUpload() {
    if (!uploadZone || !fileInput || !uploadButton) {
        console.warn("Upload UI elements not found; upload module inactive.");
        return;
    }

    uploadZone.addEventListener("click", () => fileInput.click());
    uploadZone.addEventListener("dragover", handleDragOver);
    uploadZone.addEventListener("dragleave", handleDragLeave);
    uploadZone.addEventListener("drop", handleFileDrop);

    fileInput.addEventListener("change", handleFileSelect);
    uploadButton.addEventListener("click", handleUpload);
}

function handleDragOver(event) {
    event.preventDefault();
    uploadZone.classList.add("dragover");
}

function handleDragLeave(event) {
    event.preventDefault();
    uploadZone.classList.remove("dragover");
}

function handleFileDrop(event) {
    event.preventDefault();
    uploadZone.classList.remove("dragover");
    const file = event.dataTransfer.files[0];
    if (file) {
        setSelectedFile(file);
    }
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        setSelectedFile(file);
    }
}

function setSelectedFile(file) {
    if (!file.name.endsWith(".csv")) {
        showError("Please choose a CSV file (.csv extension required).");
        return;
    }
    selectedFile = file;
    clearError();
    
    // Show file info
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    fileInfo.classList.remove("hidden");
    
    updateStatus(`Selected file: ${file.name}`);
}

function formatFileSize(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
}

async function handleUpload() {
    if (!selectedFile) {
        showError("Select a CSV file to upload.");
        return;
    }

    // Ensure any previous stream is fully closed before starting a new upload
    if (eventSource) {
        try { eventSource.close(); } catch (_) {}
        eventSource = null;
    }

    resetProgress();
    updateStatus("Uploading file…");

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
        const response = await fetch(`${API_BASE}/api/products/upload`, {
            method: "POST",
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || "Upload failed.");
        }

        const job = await response.json();
        updateStatus("File accepted. Import started…");
        startProgressStream(job.id);
    } catch (error) {
        showError(error.message || "Upload failed.");
        // Keep file info visible on error so user can retry
        return;
    }
}

function startProgressStream(jobId) {
    if (eventSource) {
        try { eventSource.close(); } catch (_) {}
        eventSource = null;
    }

    progressContainer.classList.remove("hidden");
    appendLog(`Job ${jobId} started.`);

    // Cache-bust the SSE URL to avoid any connection reuse issues between consecutive uploads
    const sseUrl = `${API_BASE}/api/progress/${jobId}?v=${Date.now()}`;
    eventSource = new EventSource(sseUrl);
    eventSource.onopen = () => appendLog("Connected to progress stream.");

    eventSource.addEventListener("progress", (event) => {
        const data = parseEventData(event.data);
        if (!data) {
            console.warn("Failed to parse progress data:", event.data);
            return;
        }

        // Normalize progress value (handle both string and number)
        const progress = typeof data.progress === "string" 
            ? parseInt(data.progress, 10) || 0 
            : Number(data.progress ?? 0);
        
        const status = data.status ?? "processing";
        const message = data.message ?? "";
        
        // Handle both field name variations
        const processed = Number(data.processed_records ?? data.processed ?? 0);
        const total = Number(data.total_records ?? data.total ?? 0);

        // Debug logging (can be removed later)
        console.log("Progress update:", { progress, status, processed, total, data });

        percentageLabel.textContent = `${progress}%`;
        progressBar.style.width = `${progress}%`;

        const statusText = total > 0
            ? `${status} — ${processed}/${total} records`
            : `${status} — ${processed} processed`;
        updateStatus(statusText);

        if (message) {
            appendLog(message);
        }

        if (status === "completed" || status === "failed") {
            appendLog(`Job ${jobId} ${status}.`);
            eventSource.close();
            eventSource = null;
            
            // Hide file info after completion (with a delay for user to see final status)
            setTimeout(() => {
                fileInfo.classList.add("hidden");
                selectedFile = null;
                fileInput.value = ""; // Reset file input
            }, 2000); // Hide after 2 seconds
        }
    });

    eventSource.onerror = () => {
        appendLog("Connection lost. Retrying…");
        // Proactively close; the browser will attempt to reconnect automatically.
        try { eventSource.close(); } catch (_) {}
    };
}

function resetProgress() {
    progressContainer.classList.remove("hidden");
    progressBar.style.width = "0%";
    percentageLabel.textContent = "0%";
    logOutput.textContent = "";
    clearError();
    // Keep file info visible during processing
    if (selectedFile) {
        fileInfo.classList.remove("hidden");
    }
}

function updateStatus(text) {
    statusLabel.textContent = text;
}

function appendLog(text) {
    const timestamp = new Date().toLocaleTimeString();
    logOutput.textContent += `[${timestamp}] ${text}\n`;
    logOutput.scrollTop = logOutput.scrollHeight;
}

function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
}

function clearError() {
    errorBox.textContent = "";
    errorBox.classList.add("hidden");
}

function parseEventData(raw) {
    try {
        return JSON.parse(raw);
    } catch (error) {
        console.warn("Failed to parse SSE event data", raw);
        return null;
    }
}

