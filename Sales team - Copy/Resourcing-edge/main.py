"""
main.py - PDF Processing Pipeline
Flow: PDF -> TXT (digital_extractor) -> JSON (GPT-4o via OpenAI API)

For each PDF found in the source directory:
  1. Create a dedicated output folder  (outputs/<pdf_stem>/)
  2. Copy the original PDF into that folder
  3. Extract text  -> <pdf_stem>.extracted.txt
  4. Send text + JSON schema to GPT-4o -> <pdf_stem>.json
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

# -- Load environment variables ------------------------------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL      = os.getenv("LLM_MODEL", "gpt-4o")

# -- Logging setup -------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# -- Paths & Sys Path ----------------------------------------------------------
BASE_DIR    = Path(__file__).parent.resolve()  # folder that contains main.py
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
SCHEMA_FILE = BASE_DIR / "schema_json.txt"  # JSON schema definition
OUTPUT_ROOT = BASE_DIR / "outputs"          # parent folder for all per-PDF folders


# =============================================================================
# Step 1 - PDF -> TXT
# =============================================================================

def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extract raw text from a PDF using digital_extractor.
    Returns the combined text string.
    """
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    from digital_extractor import extract, is_digital

    logger.info("[Step 1] Extracting text from: %s", pdf_path.name)

    if not is_digital(pdf_path):
        logger.warning("  PDF appears to be scanned/image-only - OCR path will be attempted.")

    text, rotation_info, error = extract(pdf_path, max_pages=0)   # 0 = all pages

    if error:
        logger.warning("  Extraction warning: %s", error)
    logger.info("  Rotation: %s | Characters extracted: %d", rotation_info, len(text))

    if not text.strip():
        raise RuntimeError(f"No text could be extracted from {pdf_path.name}")

    return text


# =============================================================================
# Step 2 - TXT + Schema -> JSON  (GPT-4o)  — page-by-page strategy
# =============================================================================

import re as _re

def _load_schema() -> dict:
    """Load and parse the JSON schema from schema_json.txt."""
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_FILE}")
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _split_pages(text: str) -> list[str]:
    """
    Split extracted text into per-page chunks using the 'Page N' footer marker
    that pdfplumber/PyMuPDF places at the end of each page's Abbreviation Key line.
    Falls back to returning the whole text as one chunk if no markers are found.
    """
    # Split AFTER lines ending with 'Page <number>' (case-insensitive)
    parts = _re.split(r'(?im)(Page\s+\d+)\s*$', text)
    # re.split with a capturing group returns: [before, marker, before, marker, ...]
    # Re-combine: join each content piece with its trailing "Page N" marker
    pages = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        if i + 1 < len(parts) and _re.match(r'(?i)Page\s+\d+', parts[i + 1].strip()):
            chunk = chunk + parts[i + 1]  # append the "Page N" marker back
            i += 2
        else:
            i += 1
        chunk = chunk.strip()
        if chunk:
            pages.append(chunk)

    return pages if len(pages) > 1 else [text.strip()]



def _build_header_prompt(page_text: str) -> str:
    """Prompt to extract plans from page 1."""
    return f"""You are a precise data-extraction assistant for insurance documents.

This is PAGE 1 of a multi-page insurance plan comparison PDF.
Extract ALL 'Current' plan details visible on this page.

=== CRITICAL COLUMN ALIGNMENT RULE ===
This document is presented in columns representing pairs of plans (alternating 'Current' and 'Proposed' plans).
Depending on the page, there may be 4, 6, or 8 total columns of data.
To determine the number of columns, count the number of space-separated values in the Deductible or Coinsurance rows:
- **8 values:** 4 Current plans (Col 1, 3, 5, 7) and 4 Proposed plans (Col 2, 4, 6, 8)
- **6 values:** 3 Current plans (Col 1, 3, 5) and 3 Proposed plans (Col 2, 4, 6)
- **4 values:** 2 Current plans (Col 1, 3) and 2 Proposed plans (Col 2, 4)

Every benefit row (Deductible, Coinsurance, OOP Max, Copays) and rate row (Employee Only enrollment & rate) contains exactly this number of values.
You MUST align them sequentially:
  - Value 1 -> Column 1 (Current Plan 1)
  - Value 2 -> Column 2 (Proposed Plan 1 - Skip)
  - Value 3 -> Column 3 (Current Plan 2)
  - Value 4 -> Column 4 (Proposed Plan 2 - Skip)
  - Value 5 -> Column 5 (Current Plan 3)
  - Value 6 -> Column 6 (Proposed Plan 3 - Skip)
  - Value 7 -> Column 7 (Current Plan 4)
  - Value 8 -> Column 8 (Proposed Plan 4 - Skip)

=== CARRIER, PLAN NAME, AND NETWORK MAPPING ===
The header section is consolidated into exactly two rows at the top of the table:
1. **Carrier Row:** The row starting with the label `Carrier`.
   - Column 1 Carrier -> Column 1 Carrier
   - Column 3 Carrier -> Column 3 Carrier
   - Column 5 Carrier -> Column 5 Carrier
   - Column 7 Carrier -> Column 7 Carrier
2. **Plan Name & Details Row:** The row starting with the label `Plan Name & Details`. This row contains the plan name and details (including network names, if any).
   - Column 1 Plan Name & Details -> Column 1 Plan Name & Details
   - Column 3 Plan Name & Details -> Column 3 Plan Name & Details
   - Column 5 Plan Name & Details -> Column 5 Plan Name & Details
   - Column 7 Plan Name & Details -> Column 7 Plan Name & Details

For each plan, you must parse the "Plan Name & Details" value to extract:
  - `planName`: The plan name portion. Crucially, you MUST keep geographic identifiers, states, regions, or percentages (such as "UT", "FL", "Mid Atlantic%", "Midwest", "Texas", "Dallas", "Pacific NW") as part of the `planName` (e.g. "AETNA ACO 1000 UT" or "Aetna EPO 0 Central FL").
  - `network`: The network type, if present (e.g. "Choice Plus", "EPO Select", "Blue Network"). If the cell only contains the plan name and region/state (like "AETNA ACO 1000 UT"), set `network` to "N/A" (do NOT set it to the state/region abbreviation).

You MUST extract EVERY Current plan (Columns 1, 3, 5, 7 if 8 cols; Columns 1, 3, 5 if 6 cols; Columns 1, 3 if 4 cols). Do not skip or drop any Current plans!

For `prescriptionDrugs`, extract the three pharmacy tiers (Tier 1 / Tier 2 / Tier 3) separated by slashes, and strictly preserve any qualifiers like (APD), (AD), (DW) exactly as they appear in the table (e.g. '$10 (APD) / $35 (APD) / $60 (APD)').

=== OUTPUT JSON FORMAT ===
Return a JSON object with a single key: "currentPlans" — an array of plan objects.
Each plan object must strictly have this flat structure:
{{
  "carrier": "Aetna",
  "planName": "EPO 0 Central",
  "network": "Choice Plus",
  "deductible": "$1,000 / $2,000",
  "coinsurance": "20%",
  "outOfPocketMax": "$5,000 / $10,000",
  "primaryCare": "$25 (DW)",
  "specialist": "$75 (DW)",
  "emergencyRoom": "$300 / 20% (AD)",
  "urgentCare": "$75 (DW)",
  "xRayIndividualFacility": "20% (AD)",
  "prescriptionDrugs": "$10 (APD) / $45 (APD) / $75 (APD)",
  "specialtyPharmacyBenefitPerScript": "20%/40% ($250/$500 MAX) DW",
  "complexMedicalImaging": "20% (AD)",
  "additionalPharmacyDeductible": "$0",
  "employeeOnly": "4 $647.41",
  "employeeSpouse": "2 $1,567.91",
  "employeeChildren": "0 $1,426.30",
  "family": "0 $2,276.10",
  "proposedEmployeeOnly": "4 $100.00",
  "proposedEmployeeSpouse": "1 $200.00",
  "proposedEmployeeChildren": "0 $300.29",
  "proposedFamily": "0 $400.00"
}}

=== PAGE TEXT ===
{page_text}
"""


def _build_plans_only_prompt(page_text: str) -> str:
    """Prompt for pages 2+ — extract only the current plans array from this page."""
    return f"""You are a precise data-extraction assistant for insurance documents.

This is a page from a multi-page insurance plan comparison PDF.
Extract ONLY the 'Current' insurance plans visible on THIS page.

=== CRITICAL COLUMN ALIGNMENT RULE ===
This document is presented in columns representing pairs of plans (alternating 'Current' and 'Proposed' plans).
Depending on the page, there may be 4, 6, or 8 total columns of data.
To determine the number of columns, count the number of space-separated values in the Deductible or Coinsurance rows:
- **8 values:** 4 Current plans (Col 1, 3, 5, 7) and 4 Proposed plans (Col 2, 4, 6, 8)
- **6 values:** 3 Current plans (Col 1, 3, 5) and 3 Proposed plans (Col 2, 4, 6)
- **4 values:** 2 Current plans (Col 1, 3) and 2 Proposed plans (Col 2, 4)

Every benefit row (Deductible, Coinsurance, OOP Max, Copays) and rate row (Employee Only enrollment & rate) contains exactly this number of values.
You MUST align them sequentially:
  - Value 1 -> Column 1 (Current Plan 1)
  - Value 2 -> Column 2 (Proposed Plan 1 - Skip)
  - Value 3 -> Column 3 (Current Plan 2)
  - Value 4 -> Column 4 (Proposed Plan 2 - Skip)
  - Value 5 -> Column 5 (Current Plan 3)
  - Value 6 -> Column 6 (Proposed Plan 3 - Skip)
  - Value 7 -> Column 7 (Current Plan 4)
  - Value 8 -> Column 8 (Proposed Plan 4 - Skip)

=== CARRIER, PLAN NAME, AND NETWORK MAPPING ===
The header section is consolidated into exactly two rows at the top of the table:
1. **Carrier Row:** The row starting with the label `Carrier`.
   - Column 1 Carrier -> Column 1 Carrier
   - Column 3 Carrier -> Column 3 Carrier
   - Column 5 Carrier -> Column 5 Carrier
   - Column 7 Carrier -> Column 7 Carrier
2. **Plan Name & Details Row:** The row starting with the label `Plan Name & Details`. This row contains the plan name and details (including network names, if any).
   - Column 1 Plan Name & Details -> Column 1 Plan Name & Details
   - Column 3 Plan Name & Details -> Column 3 Plan Name & Details
   - Column 5 Plan Name & Details -> Column 5 Plan Name & Details
   - Column 7 Plan Name & Details -> Column 7 Plan Name & Details

For each plan, you must parse the "Plan Name & Details" value to extract:
  - `planName`: The plan name portion. Crucially, you MUST keep geographic identifiers, states, regions, or percentages (such as "UT", "FL", "Mid Atlantic%", "Midwest", "Texas", "Dallas", "Pacific NW") as part of the `planName` (e.g. "AETNA ACO 1000 UT" or "Aetna EPO 0 Central FL").
  - `network`: The network type, if present (e.g. "Choice Plus", "EPO Select", "Blue Network"). If the cell only contains the plan name and region/state (like "AETNA ACO 1000 UT"), set `network` to "N/A" (do NOT set it to the state/region abbreviation).

You MUST extract EVERY Current plan (Columns 1, 3, 5, 7 if 8 cols; Columns 1, 3, 5 if 6 cols; Columns 1, 3 if 4 cols). Do not skip or drop any Current plans!

For `prescriptionDrugs`, extract the three pharmacy tiers (Tier 1 / Tier 2 / Tier 3) separated by slashes, and strictly preserve any qualifiers like (APD), (AD), (DW) exactly as they appear in the table (e.g. '$10 (APD) / $35 (APD) / $60 (APD)').

=== OUTPUT JSON FORMAT ===
Return a JSON object with a single key: "currentPlans" — an array of plan objects.
Each plan object must strictly have this flat structure:
{{
  "carrier": "Aetna",
  "planName": "AETNA PPO 2000",
  "network": "Choice Plus",
  "deductible": "$2,000 / $4,000",
  "coinsurance": "20%",
  "outOfPocketMax": "$6,850 / $13,700",
  "primaryCare": "$30 (DW)",
  "specialist": "$60 (DW)",
  "emergencyRoom": "$500 (DW)",
  "urgentCare": "$85 (DW)",
  "xRayIndividualFacility": "20% (AD)",
  "prescriptionDrugs": "$10 (APD) / $45 (APD) / $70 (APD)",
  "specialtyPharmacyBenefitPerScript": "20%/40% ($250/$500 MAX) DW",
  "complexMedicalImaging": "20% (AD)",
  "additionalPharmacyDeductible": "$0",
  "employeeOnly": "1 $665.00",
  "employeeSpouse": "0 $1,536.00",
  "employeeChildren": "0 $1,356.00",
  "family": "0 $2,014.00",
  "proposedEmployeeOnly": "4 $100.00",
  "proposedEmployeeSpouse": "1 $200.00",
  "proposedEmployeeChildren": "0 $300.29",
  "proposedFamily": "0 $400.00"
}}

=== PAGE TEXT ===
{page_text}
"""


def _call_openai(client, prompt: str, page_label: str) -> dict:
    """Make a single GPT-4o call and return parsed JSON."""
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    raw = response.choices[0].message.content
    logger.info("  %s -> LLM responded (%d chars)", page_label, len(raw))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("  %s -> JSON parse error: %s — skipping page.", page_label, exc)
        return {}


def call_llm_for_json(extracted_text: str) -> dict:
    """
    Page-by-page strategy:
      - Page 1  : extract plans (flat structure).
      - Pages 2+ : extract plans (flat structure).
      - Merge    : combine plans from all pages.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package is not installed. Run: pip install openai")

    if not OPENAI_API_KEY:
        raise EnvironmentError("OPENAI_API_KEY is not set in the .env file.")

    pages  = _split_pages(extracted_text)
    logger.info("[Step 2] %d page chunk(s) detected — calling %s per page ...",
                len(pages), LLM_MODEL)

    client = OpenAI(
        api_key=OPENAI_API_KEY,
        timeout=120.0,
        max_retries=2,
    )

    # ── Page 1 ──────────────────────────────────────────────────────────────
    prompt1  = _build_header_prompt(pages[0])
    result   = _call_openai(client, prompt1, "Page 1")
    all_plans: list = result.get("currentPlans", [])

    # ── Pages 2+: plans only ─────────────────────────────────────────────────
    for i, page_text in enumerate(pages[1:], start=2):
        prompt_n  = _build_plans_only_prompt(page_text)
        page_data = _call_openai(client, prompt_n, f"Page {i}")
        new_plans = page_data.get("currentPlans", [])
        if new_plans:
            logger.info("  Page %d -> %d plan(s) found.", i, len(new_plans))
            all_plans.extend(new_plans)
        else:
            logger.info("  Page %d -> no plans (skipped).", i)

    # ── Merge ────────────────────────────────────────────────────────────────
    result = {"currentPlans": all_plans}
    logger.info("  Total current plans extracted: %d", len(all_plans))
    return result


def parse_rate_string(val_str: str) -> dict:
    """Parses enrollment and rate from a combined rate string (e.g. '4 $647.41' or '2 614.35')."""
    if not val_str or str(val_str).lower() in ("n/a", "null", "none"):
        return {"enrollment": 0, "rate": 0.0}

    val_clean = str(val_str).strip()
    parts = val_clean.split()

    enrollment = 0
    rate = 0.0

    for part in parts:
        part_clean = part.replace("$", "").replace(",", "").strip()
        if not part_clean:
            continue
        if "." in part_clean:
            try:
                rate = float(part_clean)
            except ValueError:
                pass
        else:
            try:
                enrollment = int(part_clean)
            except ValueError:
                try:
                    rate = float(part_clean)
                except ValueError:
                    pass
    return {"enrollment": enrollment, "rate": rate}


def format_currency(val) -> str:
    """Helper to convert numeric value or string to formatted '$X,XXX' or return as-is."""
    if val is None or val == "":
        return "N/A"
    try:
        num = float(val)
        if num == 0:
            return "$0"
        return f"${num:,.0f}" if num.is_integer() else f"${num:,.2f}"
    except (ValueError, TypeError):
        val_str = str(val).strip()
        if val_str.isdigit():
            return f"${int(val_str):,}"
        return val_str


def handle_duplicate_plan_names(plans: list) -> list:
    """
    Post-processing step to handle duplicate plan names.
    
    For each duplicate plan name found:
    - First occurrence: keep as-is
    - Second occurrence: append " -" to make it unique
    
    Returns the modified plans list with unique plan names.
    """
    seen_names = {}
    
    for plan in plans:
        plan_name = plan.get("planName", "")
        if not plan_name:
            continue
            
        if plan_name in seen_names:
            # This is a duplicate - append " -"
            plan["planName"] = f"{plan_name} -"
        else:
            # First occurrence - track it
            seen_names[plan_name] = True
    
    return plans


def post_process_json(raw_data: dict) -> dict:
    """Transforms flat raw JSON into the user's updated structure."""
    processed_plans = []

    for plan in raw_data.get("currentPlans", []):
        carrier = plan.get("carrier", "").strip()
        plan_name = plan.get("planName", "").strip()

        # Merge carrier + planName cleanly
        if carrier.lower() in plan_name.lower():
            full_plan_name = plan_name
        else:
            full_plan_name = f"{carrier} {plan_name}".strip()

        # Format deductibles & out of pockets
        deductible_str = plan.get("deductible", "N/A")
        if not deductible_str:
            deductible_str = "N/A"

        oop_str = plan.get("outOfPocketMax", "N/A")
        if not oop_str:
            oop_str = "N/A"

        # Rx Drugs
        rx_str = plan.get("prescriptionDrugs", "N/A")
        if not rx_str:
            rx_str = "N/A"

        add_deduct = plan.get("additionalPharmacyDeductible")
        if add_deduct not in (None, "", "N/A", "null"):
            formatted_deduct = format_currency(add_deduct)
            if formatted_deduct != "N/A":
                if formatted_deduct in ("$0", "$0.00"):
                    deduct_str = "0"
                else:
                    deduct_str = formatted_deduct
                rx_str = f"{deduct_str} / {rx_str}"

        # Parse rates
        ee = parse_rate_string(plan.get("employeeOnly"))
        es = parse_rate_string(plan.get("employeeSpouse"))
        ec = parse_rate_string(plan.get("employeeChildren"))
        fam = parse_rate_string(plan.get("family"))

        # Parse proposed rates if present
        prop_ee = parse_rate_string(plan.get("proposedEmployeeOnly"))
        prop_es = parse_rate_string(plan.get("proposedEmployeeSpouse"))
        prop_ec = parse_rate_string(plan.get("proposedEmployeeChildren"))
        prop_fam = parse_rate_string(plan.get("proposedFamily"))

        # Reconstruct the benefits
        in_network_benefits = {
            "deductible(Individual/Family)": deductible_str,
            "coinsurance": plan.get("coinsurance", "N/A") or "N/A",
            "outOfPocketMax(Individual/Family)": oop_str,
            "primaryCare": plan.get("primaryCare", "N/A") or "N/A",
            "specialist": plan.get("specialist", "N/A") or "N/A",
            "emergencyRoom": plan.get("emergencyRoom", "N/A") or "N/A",
            "urgentCare": plan.get("urgentCare", "N/A") or "N/A",
            "complexMedicalImaging": plan.get("complexMedicalImaging", "N/A") or "N/A",
            "prescriptionDrugs": rx_str
        }

        specialty = plan.get("specialtyPharmacyBenefitPerScript")
        if specialty and specialty.strip() and specialty.strip().lower() not in ("unknown", "n/a", "null"):
            in_network_benefits["specialtyPharmacyBenefitPerScript"] = specialty.strip()

        processed_benefits = {
            "inNetwork": in_network_benefits
        }

        # Build the plan object matching structure.json
        processed_plans.append({
            "planName": full_plan_name,
            "description": "Current",
            "coveredEmployeesAndRates": {
                "employeeOnly": ee,
                "employeeSpouse": es,
                "employeeChildren": ec,
                "family": fam
            },
            "proposedCoveredEmployeesAndRates": {
                "employeeOnly": prop_ee,
                "employeeSpouse": prop_es,
                "employeeChildren": prop_ec,
                "family": prop_fam
            },
            "benefits": processed_benefits
        })

    return {"currentplans": processed_plans}


def process_duplicate_plan_names(data: dict) -> dict:
    """
    Apply duplicate plan name handling to the final processed data structure.
    This ensures unique plan names in the final output.
    """
    if "currentplans" in data:
        data["currentplans"] = handle_duplicate_plan_names(data["currentplans"])
    return data


# =============================================================================
# Per-PDF processor
# =============================================================================

def validate_pdf_file(pdf_path: Path) -> tuple[bool, str]:
    """
    Validate if the file is a proper PDF and suitable for processing.
    
    Returns:
        (is_valid, error_message)
    """
    # Check file extension
    if pdf_path.suffix.lower() != '.pdf':
        return False, f"Invalid file format: {pdf_path.suffix}. Only PDF files are supported."
    
    # Check if file exists and is readable
    if not pdf_path.exists():
        return False, f"File not found: {pdf_path}"
    
    if pdf_path.stat().st_size == 0:
        return False, "File is empty (0 bytes)."
    
    # Try to open as PDF to validate format
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        page_count = len(doc)
        doc.close()
        
        if page_count == 0:
            return False, "PDF file contains no pages."
            
    except Exception as exc:
        return False, f"Invalid or corrupted PDF file: {exc}"
    
    return True, ""


def validate_pdf_content_for_poc(extracted_text: str) -> tuple[bool, str]:
    """
    Validate if the PDF content is suitable for insurance plan comparison POC.
    
    Checks for key indicators that this is an insurance plan comparison document
    (not just a summary of plan offerings or other insurance document).
    
    Returns:
        (is_suitable, error_message)
    """
    if not extracted_text or len(extracted_text.strip()) < 100:
        return False, "PDF contains insufficient text content for processing."
    
    text_lower = extracted_text.lower()
    
    # First check: Reject invoice/billing documents
    invoice_patterns = [
        'invoice', 'billing', 'amount due', 'total due', 'due date',
        'amount paid', 'billing period', 'premium due', 'pay by check',
        'mail check payable', 'statement', 'charges', 'balance due'
    ]
    
    invoice_matches = sum(1 for pattern in invoice_patterns if pattern in text_lower)
    if invoice_matches >= 3:
        return False, "PDF does not contain expected plan comparison structure (current vs proposed). This appears to be a general insurance document rather than a plan comparison."
    
    # Required indicators for insurance plan comparison
    required_indicators = [
        # Insurance plan related terms
        ['plan', 'insurance', 'benefit'],
        # Rate/cost related terms  
        ['rate', 'cost', 'premium', 'employee'],
        # Coverage related terms
        ['deductible', 'coinsurance', 'coverage', 'network']
    ]
    
    # At least one term from each category should be present
    missing_categories = []
    for i, category in enumerate(required_indicators):
        if not any(term in text_lower for term in category):
            missing_categories.append(i)
    
    if missing_categories:
        return False, "PDF does not contain expected plan comparison structure (current vs proposed). This appears to be a general insurance document rather than a plan comparison."
    
    # Check for plan comparison structure indicators (Current vs Proposed)
    comparison_indicators = [
        'plan and rate comparison',
        'current.*proposed', 
        'comparison for'
    ]
    
    found_comparison = any(__import__('re').search(indicator, text_lower) for indicator in comparison_indicators)
    
    # Check for enrollment data patterns (indicating actual usage comparison)
    # Plan comparisons typically show enrollment numbers with rates like "3 $1,387.32"
    import re
    enrollment_pattern = r'\b\d+\s+\$[\d,]+\.?\d*\b'
    enrollment_matches = re.findall(enrollment_pattern, extracted_text)
    
    # Check for Summary of Plan Offerings patterns (these should be rejected)
    offerings_patterns = [
        'monthly rate',  # Summary docs have "Monthly Rate" headers
        'choice plus.*n/a.*n/a.*n/a',  # Multiple N/A patterns in network sections
        'epo select.*n/a.*n/a.*n/a',   # Multiple N/A patterns in network sections
    ]
    
    offerings_matches = sum(1 for pattern in offerings_patterns if 
                           __import__('re').search(pattern, text_lower))
    
    # Check for form/application patterns (these should be rejected)
    form_indicators = ['application', 'signature', 'applicant', 'submit', 'enrollment form']
    form_count = sum(1 for indicator in form_indicators if indicator in text_lower)
    
    # STRICTER VALIDATION: Require BOTH comparison indicators AND enrollment patterns
    # This prevents invoices and other non-comparison documents from passing
    if not found_comparison or len(enrollment_matches) < 2:
        return False, "PDF does not contain expected plan comparison structure (current vs proposed). This appears to be a general insurance document rather than a plan comparison."
    
    # Additional rejections for specific document types
    if offerings_matches >= 2 or form_count >= 2:
        return False, "PDF does not contain expected plan comparison structure (current vs proposed). This appears to be a general insurance document rather than a plan comparison."
    
    return True, ""


def process_pdf(pdf_path: Path) -> Path:
    """
    Full pipeline for a single PDF:
      1. Validate PDF file format and content
      2. Create  outputs/<stem>/
      3. Copy    PDF  ->  outputs/<stem>/<stem>.pdf
      4. Extract text ->  outputs/<stem>/<stem>.extracted.txt
      5. LLM call    ->  outputs/<stem>/<stem>.json

    Returns the output folder path.
    
    Raises:
        ValueError: If file format is invalid or content is not suitable for POC
    """
    stem       = pdf_path.stem.strip()                  # e.g. "input"
    out_folder = OUTPUT_ROOT / stem                     # e.g. outputs/input/
    out_folder.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("Processing: %s  ->  %s/", pdf_path.name, out_folder.relative_to(BASE_DIR))

    # 1. Validate PDF file format
    is_valid_file, file_error = validate_pdf_file(pdf_path)
    if not is_valid_file:
        raise ValueError(f"File validation failed: {file_error}")
    
    logger.info("  ✓ File validation passed")

    # 2. Copy PDF into the output folder
    clean_pdf_name = f"{stem}{pdf_path.suffix}"
    dest_pdf = out_folder / clean_pdf_name
    if not dest_pdf.exists():
        shutil.copy2(pdf_path, dest_pdf)
        logger.info("  Copied PDF -> %s", dest_pdf.relative_to(BASE_DIR))
    else:
        logger.info("  PDF already present in output folder, skipping copy.")

    # 3. Extract text and validate content
    txt_path = out_folder / f"{stem}.extracted.txt"
    if txt_path.exists():
        logger.info("  TXT already exists - loading cached version.")
        extracted_text = txt_path.read_text(encoding="utf-8")
    else:
        extracted_text = extract_text_from_pdf(dest_pdf)
        txt_path.write_text(extracted_text, encoding="utf-8")
        logger.info("  TXT saved -> %s", txt_path.relative_to(BASE_DIR))
    
    # 4. Validate PDF content is suitable for POC
    is_suitable, content_error = validate_pdf_content_for_poc(extracted_text)
    if not is_suitable:
        raise ValueError(f"Content validation failed: {content_error}")
    
    logger.info("  ✓ Content validation passed - suitable for insurance plan comparison processing")

    # 5. LLM -> JSON
    json_path = out_folder / f"{stem}.json"
    raw_json_path = out_folder / f"{stem}.raw.json"
    if json_path.exists():
        logger.info("  JSON already exists - skipping LLM call.")
    else:
        raw_dict = call_llm_for_json(extracted_text)
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_dict, f, indent=2, ensure_ascii=False)
        logger.info("  Raw JSON saved -> %s", raw_json_path.relative_to(BASE_DIR))
        result_dict = post_process_json(raw_dict)
        
        # Apply duplicate plan name handling
        result_dict = process_duplicate_plan_names(result_dict)
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)
        logger.info("  JSON saved -> %s", json_path.relative_to(BASE_DIR))

        # Save structure.json as well to match the requested output structure flow
        struct_path = out_folder / "structure.json"
        with open(struct_path, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)
        logger.info("  structure.json saved -> %s", struct_path.relative_to(BASE_DIR))

    logger.info("  Done: %s", stem)
    return out_folder


# =============================================================================
# Entry point
# =============================================================================

def _print_usage():
    print("""
PDF -> TXT -> JSON Pipeline
===========================
Usage:
  py -3.11 main.py                         Scan current folder for all PDFs
  py -3.11 main.py <file.pdf>              Process a single PDF file
  py -3.11 main.py <folder>                Process all PDFs inside a folder
  py -3.11 main.py --help                  Show this help message

Examples:
  py -3.11 main.py "C:\\Docs\\quote.pdf"
  py -3.11 main.py "C:\\Docs\\pdfs\\"
  py -3.11 main.py

Output:
  Each PDF gets its own folder inside:  outputs\\<pdf_name>\\
    <pdf_name>.pdf             (copy of original)
    <pdf_name>.extracted.txt   (extracted text)
    <pdf_name>.json            (structured JSON via GPT-4o)

Note: Already-processed files are cached. Delete the output subfolder to reprocess.
""")


def main():
    """
    Three modes:
      1. No argument     -> scan BASE_DIR for all *.pdf
      2. Path to a file  -> process that single PDF
      3. Path to a folder -> scan that folder for all *.pdf
    """
    arg = sys.argv[1] if len(sys.argv) > 1 else None

    # Help flag
    if arg in ("--help", "-h", "/?"):
        _print_usage()
        return

    if arg is not None:
        target = Path(arg)

        # --- Single PDF file ---
        if target.is_file():
            if target.suffix.lower() != ".pdf":
                logger.error("'%s' is not a PDF file. Please pass a .pdf file.", target)
                return
            logger.info("Single-file mode: %s", target)
            try:
                process_pdf(target)
                logger.info("=" * 60)
                logger.info("Pipeline complete. 1 succeeded, 0 failed.")
            except ValueError as validation_exc:
                logger.error("Validation failed for %s: %s", target.name, validation_exc)
                logger.info("=" * 60)
                logger.info("Pipeline complete. 0 succeeded, 1 failed (validation error).")
            except Exception as exc:
                logger.error("Failed to process %s: %s", target.name, exc)
                logger.info("=" * 60)
                logger.info("Pipeline complete. 0 succeeded, 1 failed (processing error).")
            return

        # --- Folder ---
        if target.is_dir():
            scan_dir = target
        else:
            logger.error("Path not found: %s", target)
            _print_usage()
            return
    else:
        # Default: scan the project folder
        scan_dir = BASE_DIR

    # Collect PDFs (skip anything already inside outputs/)
    pdf_files = [
        p for p in scan_dir.glob("*.pdf")
        if OUTPUT_ROOT not in p.parents
    ]

    if not pdf_files:
        logger.warning("No PDF files found in: %s", scan_dir)
        _print_usage()
        return

    logger.info("Found %d PDF(s) to process in: %s", len(pdf_files), scan_dir)

    failed: list[str] = []
    validation_failed: list[str] = []
    for pdf in sorted(pdf_files):
        try:
            process_pdf(pdf)
        except ValueError as validation_exc:
            logger.error("  Validation failed for %s: %s", pdf.name, validation_exc)
            validation_failed.append(pdf.name)
        except Exception as exc:
            logger.error("  Failed to process %s: %s", pdf.name, exc)
            failed.append(pdf.name)

    logger.info("=" * 60)
    succeeded = len(pdf_files) - len(failed) - len(validation_failed)
    logger.info("Pipeline complete. %d succeeded, %d failed, %d validation errors.",
                succeeded, len(failed), len(validation_failed))
    if validation_failed:
        logger.error("Validation failed files: %s", ", ".join(validation_failed))
    if failed:
        logger.error("Processing failed files: %s", ", ".join(failed))


if __name__ == "__main__":
    main()

