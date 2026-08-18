import json
import logging
import os
import shutil
import sys
from pathlib import Path

# Ensure Resourcing-edge directory is in sys.path for local module imports
BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Import the PDF processing logic from main.py
try:
    from main import process_pdf, OUTPUT_ROOT
except ImportError as exc:
    logger.error("Failed to import process_pdf from main.py. Ensure main.py is in the same directory. Error: %s", exc)
    raise exc

app = FastAPI(
    title="Insurance PDF Parser API",
    description="API and UI to extract structured insurance plan JSON from PDF documents.",
    version="1.0.0"
)

# HTML template for the premium Web UI
HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Insurance PDF Parser</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #080b11;
            --card-bg: rgba(15, 22, 36, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --primary-glow: rgba(99, 102, 241, 0.35);
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.2);
            --error: #ef4444;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --gradient-1: #3b82f6;
            --gradient-2: #8b5cf6;
            --gradient-3: #ec4899;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            overflow-x: hidden;
            position: relative;
        }

        /* Animated background glow circles */
        .ambient-glow {
            position: absolute;
            width: 500px;
            height: 500px;
            border-radius: 50%;
            background: radial-gradient(circle, var(--primary-glow) 0%, rgba(0,0,0,0) 70%);
            filter: blur(60px);
            z-index: -1;
            pointer-events: none;
            opacity: 0.8;
            animation: float 20s ease-in-out infinite alternate;
        }

        .glow-1 {
            top: -10%;
            left: -10%;
            background: radial-gradient(circle, rgba(139, 92, 246, 0.25) 0%, rgba(0,0,0,0) 75%);
        }

        .glow-2 {
            bottom: -10%;
            right: -10%;
            background: radial-gradient(circle, rgba(236, 72, 153, 0.2) 0%, rgba(0,0,0,0) 75%);
            animation-delay: -10s;
        }

        @keyframes float {
            0% { transform: translate(0, 0) scale(1); }
            100% { transform: translate(50px, 50px) scale(1.1); }
        }

        .container {
            width: 100%;
            max-width: 600px;
            padding: 24px;
            z-index: 10;
        }

        .card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.5);
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
            overflow: hidden;
        }

        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg, var(--gradient-1), var(--gradient-2), var(--gradient-3));
        }

        .header {
            text-align: center;
            margin-bottom: 32px;
        }

        .header h1 {
            font-size: 2.2rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            margin-bottom: 10px;
            background: linear-gradient(135deg, #ffffff 40%, #a5b4fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .header p {
            color: var(--text-muted);
            font-size: 1rem;
            font-weight: 400;
        }

        /* Upload Drop Zone */
        .upload-zone {
            border: 2px dashed rgba(255, 255, 255, 0.15);
            border-radius: 16px;
            padding: 40px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            background: rgba(255, 255, 255, 0.01);
            position: relative;
        }

        .upload-zone:hover, .upload-zone.dragover {
            border-color: var(--primary);
            background: rgba(99, 102, 241, 0.05);
            box-shadow: 0 0 20px rgba(99, 102, 241, 0.1);
        }

        .upload-icon {
            width: 64px;
            height: 64px;
            margin: 0 auto 16px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
            color: var(--text-muted);
        }

        .upload-zone:hover .upload-icon {
            background: var(--primary);
            color: #fff;
            transform: translateY(-4px);
            box-shadow: 0 8px 20px var(--primary-glow);
        }

        .upload-zone svg {
            width: 28px;
            height: 28px;
            fill: none;
            stroke: currentColor;
            stroke-width: 2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .upload-text {
            font-size: 1.1rem;
            font-weight: 500;
            margin-bottom: 8px;
        }

        .upload-hint {
            font-size: 0.85rem;
            color: var(--text-muted);
        }

        #fileInput {
            display: none;
        }

        /* Selected file banner */
        .file-banner {
            margin-top: 20px;
            padding: 14px 20px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            animation: fadeIn 0.3s ease;
        }

        .file-banner-info {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .file-banner-icon {
            color: var(--primary);
            display: flex;
        }

        .file-banner-name {
            font-size: 0.95rem;
            font-weight: 500;
            max-width: 300px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .file-remove-btn {
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            transition: color 0.2s;
            display: flex;
        }

        .file-remove-btn:hover {
            color: var(--error);
        }

        /* Action Buttons */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            padding: 16px 24px;
            font-family: inherit;
            font-size: 1.05rem;
            font-weight: 600;
            border-radius: 14px;
            border: none;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            gap: 10px;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--primary) 0%, #4f46e5 100%);
            color: white;
            box-shadow: 0 4px 20px var(--primary-glow);
            margin-top: 24px;
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(99, 102, 241, 0.5);
        }

        .btn-primary:active {
            transform: translateY(0);
        }

        .btn-success {
            background: linear-gradient(135deg, var(--success) 0%, #059669 100%);
            color: white;
            box-shadow: 0 4px 20px var(--success-glow);
            margin-top: 20px;
        }

        .btn-success:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(16, 185, 129, 0.4);
        }

        /* Loader & Processing status */
        .loader-container {
            display: none;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            margin: 32px 0;
            animation: fadeIn 0.3s ease;
        }

        .spinner {
            width: 60px;
            height: 60px;
            border: 4px solid rgba(255, 255, 255, 0.05);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 1s infinite linear;
            margin-bottom: 20px;
            position: relative;
        }

        .spinner::after {
            content: '';
            position: absolute;
            top: -4px;
            left: -4px;
            right: -4px;
            bottom: -4px;
            border: 4px solid transparent;
            border-top-color: var(--gradient-3);
            border-radius: 50%;
            animation: spin 2.5s infinite linear;
        }

        .loader-text {
            font-size: 1.1rem;
            font-weight: 500;
            margin-bottom: 6px;
            color: var(--text-main);
        }

        .loader-subtext {
            font-size: 0.85rem;
            color: var(--text-muted);
            animation: pulse 1.5s infinite ease-in-out;
        }

        /* Result View */
        .result-container {
            display: none;
            animation: slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }

        .success-banner {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            padding: 20px 0;
        }

        .success-badge {
            width: 72px;
            height: 72px;
            background: rgba(16, 185, 129, 0.1);
            border: 2px solid var(--success);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--success);
            margin-bottom: 16px;
            box-shadow: 0 0 25px rgba(16, 185, 129, 0.2);
            animation: scaleIn 0.5s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .success-badge svg {
            width: 36px;
            height: 36px;
            stroke-width: 3;
        }

        .result-title {
            font-size: 1.4rem;
            font-weight: 600;
            margin-bottom: 8px;
        }

        .result-desc {
            font-size: 0.95rem;
            color: var(--text-muted);
            margin-bottom: 24px;
        }

        /* JSON visualizer preview box */
        .preview-box {
            background: rgba(0, 0, 0, 0.35);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            max-height: 150px;
            overflow-y: auto;
            text-align: left;
            font-family: monospace;
            font-size: 0.8rem;
            color: #a5b4fc;
            margin-bottom: 20px;
            scrollbar-width: thin;
            scrollbar-color: rgba(255,255,255,0.1) transparent;
        }

        .preview-box::-webkit-scrollbar {
            width: 6px;
        }
        .preview-box::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.1);
            border-radius: 3px;
        }

        /* Error state styling */
        .error-container {
            display: none;
            background: rgba(239, 68, 68, 0.05);
            border: 1px solid rgba(239, 68, 68, 0.2);
            border-radius: 16px;
            padding: 20px;
            margin-top: 20px;
            animation: fadeIn 0.3s ease;
        }

        .error-header {
            display: flex;
            align-items: center;
            gap: 10px;
            color: var(--error);
            font-weight: 600;
            margin-bottom: 8px;
        }

        .error-message {
            font-size: 0.9rem;
            color: var(--text-muted);
            line-height: 1.4;
        }

        /* Animations */
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        @keyframes pulse {
            0%, 100% { opacity: 0.6; }
            50% { opacity: 1; }
        }

        @keyframes slideUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes scaleIn {
            from { opacity: 0; transform: scale(0.8); }
            to { opacity: 1; transform: scale(1); }
        }

        .footer-note {
            text-align: center;
            margin-top: 24px;
            font-size: 0.8rem;
            color: rgba(255,255,255,0.25);
        }

        .footer-note a {
            color: rgba(255,255,255,0.4);
            text-decoration: none;
            transition: color 0.2s;
        }

        .footer-note a:hover {
            color: var(--primary);
        }
    </style>
</head>
<body>
    <div class="ambient-glow glow-1"></div>
    <div class="ambient-glow glow-2"></div>

    <div class="container">
        <div class="card">
            <!-- Header section -->
            <div class="header" id="cardHeader">
                <h1>Insurance PDF Parser</h1>
                <p>Upload a benefits summary PDF to extract structured plan details</p>
            </div>

            <!-- Upload state -->
            <div id="uploadContainer">
                <div class="upload-zone" id="dropZone">
                    <input type="file" id="fileInput" accept=".pdf">
                    <div class="upload-icon">
                        <svg viewBox="0 0 24 24">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                        </svg>
                    </div>
                    <div class="upload-text">Drag & drop your PDF file</div>
                    <div class="upload-hint">or click to browse from files</div>
                </div>

                <!-- Banner when a file is staged -->
                <div class="file-banner" id="fileBanner" style="display: none;">
                    <div class="file-banner-info">
                        <span class="file-banner-icon">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                                <polyline points="14 2 14 8 20 8"/>
                            </svg>
                        </span>
                        <span class="file-banner-name" id="fileName">document.pdf</span>
                    </div>
                    <button class="file-remove-btn" id="removeFileBtn" title="Remove file">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="18" y1="6" x2="6" y2="18"/>
                            <line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                    </button>
                </div>

                <!-- Convert button -->
                <button class="btn btn-primary" id="convertBtn" style="display: none;">
                    <span>Extract Benefits & Rates</span>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="9 18 15 12 9 6"/>
                    </svg>
                </button>
            </div>

            <!-- Loader / Processing state -->
            <div class="loader-container" id="loaderContainer">
                <div class="spinner"></div>
                <div class="loader-text">Analyzing PDF Document</div>
                <div class="loader-subtext" id="loaderSubtext">Running text extraction pipeline...</div>
            </div>

            <!-- Error banner -->
            <div class="error-container" id="errorContainer">
                <div class="error-header">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="8" x2="12" y2="12"/>
                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                    <span>Parsing Failed</span>
                </div>
                <div class="error-message" id="errorMessage">An unexpected error occurred. Please try again.</div>
                <button class="btn btn-primary" id="retryBtn" style="margin-top: 16px;">Try Again</button>
            </div>

            <!-- Result state -->
            <div class="result-container" id="resultContainer">
                <div class="success-banner">
                    <div class="success-badge">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <polyline points="20 6 9 17 4 12"/>
                        </svg>
                    </div>
                    <div class="result-title">Processing Complete</div>
                    <div class="result-desc" id="resultDesc">Your structured benefits scheme has been successfully created.</div>
                </div>
                
                <div class="preview-box" id="jsonPreview"></div>

                <button class="btn btn-success" id="downloadBtn">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
                    </svg>
                    <span>Download JSON Schema</span>
                </button>
                
                <button class="btn" id="newFileBtn" style="margin-top: 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); color: var(--text-main);">
                    Parse Another Document
                </button>
            </div>
        </div>

        <div class="footer-note">
            Powering insurance data extraction. API docs at <a href="/docs" target="_blank">/docs</a>.
        </div>
    </div>

    <script>
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const fileBanner = document.getElementById('fileBanner');
        const fileName = document.getElementById('fileName');
        const removeFileBtn = document.getElementById('removeFileBtn');
        const convertBtn = document.getElementById('convertBtn');
        const uploadContainer = document.getElementById('uploadContainer');
        const loaderContainer = document.getElementById('loaderContainer');
        const loaderSubtext = document.getElementById('loaderSubtext');
        const resultContainer = document.getElementById('resultContainer');
        const resultDesc = document.getElementById('resultDesc');
        const jsonPreview = document.getElementById('jsonPreview');
        const downloadBtn = document.getElementById('downloadBtn');
        const errorContainer = document.getElementById('errorContainer');
        const errorMessage = document.getElementById('errorMessage');
        const retryBtn = document.getElementById('retryBtn');
        const newFileBtn = document.getElementById('newFileBtn');
        const cardHeader = document.getElementById('cardHeader');

        let selectedFile = null;
        let processedData = null;
        let fileStem = '';

        // Subtext updates during conversion to keep user updated and feel responsive
        const subtexts = [
            "Extracting characters from digital layout...",
            "Running alignment algorithms on tables...",
            "Consulting LLM parser with custom scheme...",
            "Post-processing employee enrollment & rates...",
            "Formatting currency values...",
            "Validating structure compliance..."
        ];
        let subtextInterval = null;

        function showError(title, message) {
            // Hide other containers
            uploadContainer.style.display = 'none';
            loaderContainer.style.display = 'none';
            resultContainer.style.display = 'none';
            
            // Update error content
            const errorHeader = errorContainer.querySelector('.error-header span');
            const errorMsg = errorContainer.querySelector('.error-message');
            errorHeader.textContent = title;
            errorMsg.textContent = message;
            
            // Show error
            errorContainer.style.display = 'block';
        }

        function startLoaderAnimation() {
            let index = 0;
            loaderSubtext.innerText = subtexts[0];
            subtextInterval = setInterval(() => {
                index = (index + 1) % subtexts.length;
                loaderSubtext.innerText = subtexts[index];
            }, 3000);
        }

        function stopLoaderAnimation() {
            clearInterval(subtextInterval);
        }

        // Drag & Drop behaviors
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
            }, false);
        });

        dropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length) {
                handleFileSelect(files[0]);
            }
        });

        dropZone.addEventListener('click', () => {
            fileInput.click();
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) {
                handleFileSelect(e.target.files[0]);
            }
        });

        function handleFileSelect(file) {
            if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
                showError('Invalid File Format', 'Only PDF files are supported. Please select a valid PDF file.');
                return;
            }
            selectedFile = file;
            fileName.innerText = file.name;
            dropZone.style.display = 'none';
            fileBanner.style.display = 'flex';
            convertBtn.style.display = 'inline-flex';
        }

        removeFileBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            resetUploadState();
        });

        function resetUploadState() {
            selectedFile = null;
            fileInput.value = '';
            dropZone.style.display = 'block';
            fileBanner.style.display = 'none';
            convertBtn.style.display = 'none';
        }

        // Trigger conversion process
        convertBtn.addEventListener('click', async () => {
            if (!selectedFile) return;

            // Hide upload items, show loading
            uploadContainer.style.display = 'none';
            errorContainer.style.display = 'none';
            loaderContainer.style.display = 'flex';
            startLoaderAnimation();

            const formData = new FormData();
            formData.append('file', selectedFile);

            try {
                const response = await fetch('/process-pdf', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const errDetail = await response.json().catch(() => ({detail: {error_type: 'unknown_error', message: 'Unknown backend error'}}));
                    
                    // Handle different error types
                    const errorInfo = errDetail.detail || errDetail;
                    const errorType = errorInfo.error_type || 'unknown_error';
                    const errorMessage = errorInfo.message || errorInfo || `Server error (${response.status})`;
                    
                    let errorTitle = 'Processing Failed';
                    let userMessage = errorMessage;
                    
                    switch(errorType) {
                        case 'invalid_file_format':
                            errorTitle = 'Invalid File Format';
                            userMessage = 'Only PDF files are supported. Please select a valid PDF document.';
                            break;
                        case 'invalid_pdf_file':
                            errorTitle = 'Invalid PDF File';
                            userMessage = 'The uploaded file is corrupted or not a valid PDF. Please try with a different file.';
                            break;
                        case 'unsuitable_content':
                            errorTitle = 'Document Not Suitable';
                            userMessage = 'This PDF does not contain expected plan comparison structure (current vs proposed). Please upload a Plan and Rate Comparison document.';
                            break;
                        case 'file_save_error':
                            errorTitle = 'Upload Failed';
                            userMessage = 'Failed to save the uploaded file. Please try again.';
                            break;
                        case 'processing_error':
                            errorTitle = 'Processing Error';
                            userMessage = 'An error occurred while processing your document. Please try again or contact support.';
                            break;
                        default:
                            errorTitle = 'Processing Failed';
                            userMessage = errorMessage;
                    }
                    
                    throw new Error(`${errorTitle}: ${userMessage}`);
                }

                processedData = await response.json();
                
                // Get stem (filename without extension)
                fileStem = selectedFile.name.replace(/\.[^/.]+$/, "");

                // Finish loading and render results
                stopLoaderAnimation();
                loaderContainer.style.display = 'none';
                
                // Set details in preview
                jsonPreview.innerText = JSON.stringify(processedData, null, 2);
                resultDesc.innerText = `Successfully parsed "${selectedFile.name}" into structured JSON.`;
                resultContainer.style.display = 'block';
            } catch (err) {
                stopLoaderAnimation();
                loaderContainer.style.display = 'none';
                
                // Parse error message to separate title and message
                const errorText = err.message;
                const colonIndex = errorText.indexOf(': ');
                let errorTitle = 'Processing Failed';
                let errorMessage = errorText;
                
                if (colonIndex > 0) {
                    errorTitle = errorText.substring(0, colonIndex);
                    errorMessage = errorText.substring(colonIndex + 2);
                }
                
                showError(errorTitle, errorMessage);
            }
        });

        // Download event handling
        downloadBtn.addEventListener('click', () => {
            if (!processedData || !fileStem) return;
            
            // Trigger direct download of the processed JSON payload
            const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(processedData, null, 2));
            const downloadAnchor = document.createElement('a');
            downloadAnchor.setAttribute("href", dataStr);
            downloadAnchor.setAttribute("download", `${fileStem}.json`);
            document.body.appendChild(downloadAnchor);
            downloadAnchor.click();
            downloadAnchor.remove();
        });

        // Retry and Reset
        retryBtn.addEventListener('click', () => {
            errorContainer.style.display = 'none';
            uploadContainer.style.display = 'block';
            resetUploadState();
        });

        newFileBtn.addEventListener('click', () => {
            resultContainer.style.display = 'none';
            uploadContainer.style.display = 'block';
            resetUploadState();
        });
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def serve_home():
    """Serves the premium, responsive Web UI."""
    return HTML_CONTENT

@app.get("/health")
async def health_check():
    """Simple status check endpoint."""
    return {"status": "healthy"}

@app.post("/process-pdf")
@app.post("/api/process-pdf")
async def process_pdf_endpoint(request: Request, file: UploadFile = File(...)):
    """
    Upload a single PDF, process it through the extraction & LLM pipeline,
    and return the final processed JSON directly.
    """
    # Validate file extension
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail={
                "error_type": "invalid_file_format",
                "message": f"Invalid file format. Only PDF files are supported, but received '{file.filename}'."
            }
        )

    clean_filename = file.filename.strip()
    incoming_dir = OUTPUT_ROOT / "incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = incoming_dir / clean_filename

    logger.info("Saving uploaded file to: %s", pdf_path)
    try:
        # Stream file to local incoming/ directory
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        logger.error("Failed to save uploaded file: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": "file_save_error", 
                "message": f"Failed to save uploaded file on server: {exc}"
            }
        )

    try:
        # Run processing pipeline (includes validation)
        out_folder = process_pdf(pdf_path)
        
        # Read the resulting JSON schema from output folder
        stem = pdf_path.stem.strip()
        json_path = out_folder / f"{stem}.json"
        
        if not json_path.exists():
            raise RuntimeError(f"Processing finished, but the expected JSON was not found at {json_path}")
            
        with open(json_path, "r", encoding="utf-8") as f:
            processed_data = json.load(f)

        try:
            from database import poc_db
            processed_by = request.headers.get("X-Processed-By") or request.query_params.get("processed_by") or "SYSTEM"
            poc_db.log_resourcing_run(file.filename, "SUCCESS", pdf_path.stem, f"{pdf_path.stem}.json", processed_by=processed_by)
            print(f"[DB] Logged Resourcing Edge run for {file.filename} to converter.db", flush=True)
        except Exception as db_err:
            print(f"[WARN] Failed to log Resourcing Edge run to DB: {db_err}", flush=True)
            
        return processed_data
        
    except ValueError as validation_exc:
        # Handle validation errors (file format or content validation)
        error_message = str(validation_exc)
        logger.error("Validation error: %s", error_message)
        
        if "File validation failed" in error_message:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_type": "invalid_pdf_file",
                    "message": error_message
                }
            )
        elif "Content validation failed" in error_message:
            raise HTTPException(
                status_code=422,  # Unprocessable Entity
                detail={
                    "error_type": "unsuitable_content",
                    "message": error_message
                }
            )
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_type": "validation_error",
                    "message": error_message
                }
            )
            
    except Exception as exc:
        logger.error("Error occurred during PDF pipeline run: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": "processing_error",
                "message": f"Pipeline error: {str(exc)}"
            }
        )

@app.get("/download/{pdf_stem}")
async def download_processed_file(pdf_stem: str):
    """
    Exposes direct file download capability. Searches for processed JSON
    for a given pdf_stem and returns it as a direct attachment file.
    """
    clean_stem = pdf_stem.strip()
    json_path = OUTPUT_ROOT / clean_stem / f"{clean_stem}.json"
    if not json_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No processed JSON found for the file stem '{clean_stem}'. Please make sure you process the PDF first."
        )
    return FileResponse(
        path=json_path,
        media_type="application/json",
        filename=f"{clean_stem}.json"
    )

@app.get("/history")
@app.get("/api/history")
async def get_resourcing_history(limit: int = 50):
    """Return recent Resourcing Edge processing history from the shared DB."""
    try:
        from database import poc_db
        conns = poc_db.get_connections()
        for conn in conns:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, pdf_filename, status, plan_names, output_json, error_message, created_date "
                "FROM resourcing_history ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        return []
    except Exception as exc:
        logger.warning("Could not fetch resourcing history: %s", exc)
        return []

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
