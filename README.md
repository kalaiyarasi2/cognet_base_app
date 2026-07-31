# CogNet - Unified AI-Powered Document Processing System

CogNet is a comprehensive, enterprise-level document processing pipeline that integrates multiple AI-powered sub-applications for extracting structured data from business documents, emails, and PDF attachments. This unified system automates the entire workflow from email ingestion through document classification to intelligent data extraction and output generation.

## Overview

CogNet combines five specialized AI modules into a single integrated platform:

- **Parity_setup**: Parses and extracts information from Sales Benefit Contracts
- **Renewal_process**: Processes renewal premium invoices and insurance documents
- **Resourcing-edge**: Extracts insurance claims and work compensation data
- **rpve**: Consolidates vendor invoices and RPVE (Risk Protection Value Estimate) documents
- **File-Convertor**: Handles universal document format conversion
- **AI Classifier**: Advanced document category classification using multiple AI models

### How It Works

1. **Email Ingestion**: Automatically polls emails from Outlook/Gmail
2. **Document Classification**: Analyzes PDF attachments and categorizes them
3. **Intelligent Routing**: Routes documents to appropriate parsers based on category
4. **Data Extraction**: Extracts structured data from classified documents
5. **Output Generation**: Creates organized outputs (JSON, Excel, etc.)
6. **Monitoring & Logging**: Tracks pipeline performance and issues

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- API keys for OpenAI and Azure/Microsoft AD

### Installation

```bash
# Clone the repository
cognet git clone <repository-url>

# Navigate to the project
cd CogNet

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
pip install python-dotenv
python -c "from dotenv import dotenv_values; print(dotenv_values('.env'))"

# Create .env file with required keys:
OPENAI_API_KEY=your_openai_key
MICROSOFT_CLIENT_ID=your_azure_client_id
MICROSOFT_CLIENT_SECRET=your_azure_client_secret
MICROSOFT_TENANT_ID=your_azure_tenant_id
```

### Running the Unified Server

```bash
python app.py
```

**Access the dashboard**:
- Main Dashboard: `http://localhost:8000/`
- API Documentation: `http://localhost:8000/docs`

### Running the Email Pipeline

```bash
# Run with Outlook (one-time execution)
python start_flow.py --provider outlook

# Run with Gmail (one-time execution)
python start_flow.py --provider gmail

# Run continuously (polls every 60 seconds by default)
python start_flow.py --provider outlook --interval 60
```

## 📂 Directory Structure

```
CogNet/
├── app.py                         # Unified API server (mounts all sub-apps)
├── start_flow.py                  # Unified orchestrator for email pipelines
├── connector.py                   # Outlook-specific pipeline runner
├── .env                          # Environment variables
├── requirements.txt               # All dependencies
├── logs/                         # Application logs
├── output/                       # Generated output files
├── temp_uploads/                 # Temporary file uploads
├── monitor/                      # Pipeline monitoring
└── database/                     # SQLite database for monitoring

├── Parity_setup/                  # Sales Contract Parser
├── Renewal_process/               # Renewal Premium Processor
├── Resourcing-edge/                # Insurance Claims Extractor
├── rpve/                          # Invoice Consolidator
├── File-Convertor/                # Universal Format Converter
├── file-classification-/          # AI Document Classifier
├── frontend/                      # Web UI dashboard
└── Outlook_Agent/                 # Outlook automation module
```

## 📊 Data Processing Flow

| Document Type | Classifier | Parser | Output Format | Typical Use Case |
|---------------|------------|--------|---------------|------------------|
| SBC/PARITY    | AI Classify| Parity_setup | Excel + JSON | Sales Benefit Contracts |
| RENEWAL       | AI Classify| Renewal_process | JSON rates | Premium Renewal Invoices |
| INSURANCE_CLAIMS / WORK_COMP | AI Classify| Resourcing-edge | Excel + Plan JSON | Claims Documentation |
| INVOICE / RPVE / VENDOR_INVOICE | AI Classify| rpve | Consolidated Excel + JSON | Vendor Billing |
| OTHERS / BANK_STATEMENT | AI Classify| SKIPPED | Original PDF | Unclassified Documents |

## 🛠 Features

### Unified Server

- **REST API**: Single endpoint serving all sub-applications
- **Swagger UI**: Interactive API documentation
- **Sub-app Endpoints**: Dedicated APIs for each parser module
- **Health Monitoring**: Built-in health checks and status reporting

### Email Pipeline

- **Dual Provider Support**: Outlook and Gmail integration
- **Smart Classification**: AI-powered document categorization
- **Structured Storage**: Organized document routing and storage
- **Database Logging**: Comprehensive tracking of all pipeline activities

### Monitoring & Logging

- **Database Tracking**: All operations logged in SQLite
- **Real-time Status**: Monitor pipeline execution
- **Error Reporting**: Detailed error tracking and reporting

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for LLM operations |
| `MICROSOFT_CLIENT_ID` | Yes | Azure/Microsoft AD client ID |
| `MICROSOFT_CLIENT_SECRET` | Yes | Azure/Microsoft AD client secret |
| `MICROSOFT_TENANT_ID` | Yes | Azure/Microsoft AD tenant ID |

### Pipeline Configuration

- **Polling Interval**: Configurable (default: 60 seconds)
- **Document Retention**: Configurable storage periods
- **Classification Confidence**: Adjustable thresholds
- **Output Directory Structure**: Customizable organization

## 🔌 Supported Integrations

### Email Services

- **Microsoft Outlook** (via Graph API)
- **Gmail** (via Google Sheets API)

### Cloud Storage

- **Google Drive** (for backups and retrieval)
- **OneDrive** (for structured document storage)

### Output Formats

- **JSON**: Structured data extraction
- **Excel**: Spreadsheet generation
- **PDF**: Original document preservation
- **Text**: Plain text extraction

## 📈 Performance & Scalability

- **Asynchronous Processing**: Non-blocking operations
- **Batch Processing**: Efficient handling of multiple documents
- **Error Resilience**: Automatic retry and fallback mechanisms
- **Resource Monitoring**: CPU, memory, and disk usage tracking

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=. --cov-report=html
```

## 📚 Documentation

### Additional Resources

- [API Reference](/docs/api.md)
- [Pipeline Configuration](/docs/pipeline_config.md)
- [Troubleshooting Guide](/docs/troubleshooting.md)
- [Deployment Guide](/docs/deployment.md)

### Dependencies

All dependencies are listed in `requirements.txt` and include:

- **Web & API**: FastAPI, Uvicorn, Pytest
- **PDF Processing**: PyPDF2, pdfplumber, PyMuPDF
- **OCR & Vision**: Pillow, OpenCV, python-doctr
- **AI/ML**: OpenAI, PyTorch, scikit-learn
- **Data Processing**: pandas, numpy, sqlalchemy
- **Cloud & APIs**: google-api-python-client, msal
- **Utilities**: python-dotenv, tqdm, rapidfuzz

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Implement your changes
4. Run tests locally
5. Submit a pull request

## 📝 License

This project is under development. All rights reserved.
