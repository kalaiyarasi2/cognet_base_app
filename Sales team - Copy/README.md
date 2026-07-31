# Unified Sales Team Workspace

Consolidated pipeline and server orchestrating SBC Intellect, Renewal Audit, Insurance Plan Parser, Benefit Invoice Extractor, and AI Classification services.

---

## 🚀 Setup Instructions

### 1. Install Dependencies
Before running the server or pipeline runner, ensure all requirements are installed:
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Ensure you have a `.env` file at the root containing:
* `OPENAI_API_KEY`: Your OpenAI API key for LLM operations.
* Azure/Microsoft AD credentials (needed for Outlook Agent):
  * `MICROSOFT_CLIENT_ID` (or `AZURE_CLIENT_ID`)
  * `MICROSOFT_CLIENT_SECRET` (or `AZURE_CLIENT_SECRET`)
  * `MICROSOFT_TENANT_ID` (or `AZURE_TENANT_ID`)

---

## 🖥️ Running the Unified Server

Start the combined API server that mounts all sub-applications (Parity_setup, Renewal_process, Resourcing-edge, rpve, File-Convertor, file-classification-):

```bash
python app.py
```
* **Host**: `http://localhost:8000`
* **Swagger Documentation**: `http://localhost:8000/docs`

### Sub-app Endpoints
* **AI File Classifier UI**: `http://localhost:8000/` (serves the main dashboard)
* **SBC (Parity_setup) API**: `http://localhost:8000/api/parity/docs`
* **Renewal Premium API**: `http://localhost:8000/api/renewal/docs`
* **Insurance PDF Parser (Resourcing-edge) API**: `http://localhost:8000/api/resourcing/docs`
* **Benefit Invoice Extractor (rpve) API**: `http://localhost:8000/api/rpve/docs`
* **Universal Format Converter API**: `http://localhost:8000/api/convert/docs`

---

## 🔄 Running the Email Pipelines

The pipeline runner polls emails, classifies PDF attachments, saves them into structured local/OneDrive directories, and routes them to the correct backend parser.

### Using `start_flow.py` (Unified Orchestrator)
Runs the orchestrator that integrates Gmail/Outlook polling, Document Classification, Local extraction routing, and Monitoring Database logging.

* **Run once using Outlook**:
  ```bash
  python start_flow.py --provider outlook
  ```
* **Run once using Gmail**:
  ```bash
  python start_flow.py --provider gmail
  ```
* **Run continuously (polls every 60 seconds)**:
  ```bash
  python start_flow.py --provider outlook --interval 60
  ```

### Using `connector.py` (Outlook-specific Pipeline)
Runs the Outlook-to-OneDrive pipeline runner:
```bash
python connector.py
```
*(Also callable via `python connecor.py` to handle the typo).*

---

## 🏷️ Extraction Routing Rules

Based on the document category classification and text inspection, the pipeline routes PDFs to:

| Category | Extractor Project | Output Artifacts |
| :--- | :--- | :--- |
| **SBC / PARITY** | `Parity_setup` | Excel sheets & Schema JSON |
| **RENEWAL** | `Renewal_process` | Extracted premium rates JSON |
| **INSURANCE_CLAIMS / WORK_COMPENSATION** | `Resourcing-edge` | Excel sheet & Plan JSON |
| **INVOICE / RPVE / VENDOR_INVOICE** | `rpve` | Consolidated Excel sheet & JSON |
| **OTHERS / BANK_STATEMENT** | *Skipped* | Original PDF saved under Others |
