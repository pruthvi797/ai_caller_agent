"""
Document Processing Service — Universal Multimodal Extraction
=============================================================

Strategy: OpenAI Vision PRIMARY → PyMuPDF FALLBACK

Supports all car dealership document types:
  - Car Brochures       (PDF, DOCX, images) — multi-page, image-heavy, variant tables
  - Pricing Sheets      (PDF, DOCX)         — variant × price grids, ex-showroom/on-road
  - Feature Comparisons (PDF, DOCX)         — tick/cross grids across variants
  - Promotional Offers  (PDF, images)       — discounts, EMI schemes, exchange bonuses
  - Spec Sheets         (PDF, DOCX)         — engine, dimensions, transmission data
  - Service Documents   (PDF, DOCX)         — warranty, AMC, service schedule

Pipeline (OpenAI Vision primary for best quality):
  PDF   → render each page to PNG → OpenAI Vision with type-specific prompt
            → If OpenAI fails (API error / quota) → PyMuPDF text fallback for that page
  DOCX  → python-docx for text + tables; embedded images → OpenAI Vision
  Image → send directly to OpenAI Vision

Why OpenAI Vision as primary:
  - Car brochures are designed PDFs — multi-column layouts, pricing tables, image captions
  - OpenAI Vision understands layout and structure; PyMuPDF dumps raw characters
  - Consistent quality across all page types (text-heavy + image-heavy treated the same)
  - gpt-4o-mini: ~$0.00015 per image — 6-page brochure costs ~$0.001
  - PyMuPDF fallback ensures zero silent failures

Install:
  pip install openai pymupdf pillow python-docx --break-system-packages

.env:
  OPENAI_API_KEY=sk-...your_key_here
"""

import os
import re
import time
import uuid
import base64
import hashlib
import logging
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.document_model import Document
from app.models.document_chunk_model import DocumentChunk

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Model options:
#   "gpt-4o-mini"  → cheapest, fast, good for most brochures    ~$0.00015/image
#   "gpt-4o"       → best quality, ideal for dense tables/grids ~$0.00150/image
OPENAI_MODEL    = "gpt-4o-mini"

PAGE_DPI        = 150
MAX_PAGES       = 40
CHUNK_SIZE      = 800
MIN_CHUNK_CHARS = 50

# ── PyMuPDF-first threshold ────────────────────────────────────────────────────
# Pages with >= this many extracted characters skip the OpenAI Vision call.
# Pages below this are assumed scanned/image-only → OpenAI Vision.
# Set to 10 so even sparse cover pages with a few words skip the API call.
MIN_TEXT_THRESHOLD = 10

# ── Rate limiting ──────────────────────────────────────────────────────────────
# OpenAI tier-1: 500 RPM for gpt-4o-mini. 0.5s gap is very conservative.
OPENAI_MIN_INTERVAL_SECONDS = 0.5
_last_openai_call_time: float = 0.0

# ── In-process page cache ──────────────────────────────────────────────────────
# MD5(image_bytes) → extracted text. Prevents duplicate API calls when the
# same document is reprocessed within the same server process.
_page_cache: Dict[str, str] = {}

# ── Document type detection keywords ──────────────────────────────────────────
DOC_TYPE_SIGNALS = {
    "pricing_sheet":      ["price", "ex-showroom", "on-road", "variant price", "price list",
                           "lxi", "vxi", "zxi", "alpha", "delta", "sigma", "zeta"],
    "feature_comparison": ["features list", "feature comparison", "legend", "available",
                           "not available", "tick", "variant wise"],
    "promotional_offer":  ["offer", "discount", "cashback", "exchange bonus", "emi",
                           "festive", "scheme", "limited period", "save", "benefit"],
    "spec_sheet":         ["specifications", "dimensions", "engine", "transmission",
                           "wheelbase", "kerb weight", "fuel tank", "tyre size"],
    "brochure":           ["overview", "highlights", "why choose", "more power", "designed for"],
    "warranty":           ["warranty", "extended warranty", "amc", "annual maintenance",
                           "service schedule", "free service"],
}

# ── Section classification keywords ───────────────────────────────────────────
SECTION_KEYWORDS = {
    "pricing":        ["price", "ex-showroom", "on-road", "emi", "finance", "cost",
                       "lakh", "₹", "variant", "amount", "rate"],
    "features":       ["feature", "infotainment", "touchscreen", "sunroof", "camera",
                       "cruise", "climate", "wireless", "android", "apple carplay",
                       "smartplay", "ambient", "charging"],
    "safety":         ["safety", "airbag", "abs", "esp", "ncap", "rating", "brake",
                       "seatbelt", "collision", "isofix", "hill hold", "ebd", "tect"],
    "specifications": ["engine", "displacement", "cc", "bhp", "ps", "torque", "nm",
                       "mileage", "kmpl", "km/kg", "transmission", "wheelbase",
                       "ground clearance", "boot space", "fuel tank", "kerb weight",
                       "length", "width", "height", "seating", "dimensions"],
    "overview":       ["overview", "introduction", "about", "highlights", "key points",
                       "why choose", "all-new", "designed", "power to play", "tagline"],
    "warranty":       ["warranty", "service", "maintenance", "annual", "years",
                       "km coverage", "roadside", "amc", "free service"],
    "offers":         ["offer", "discount", "cashback", "exchange", "bonus", "festive",
                       "promotion", "scheme", "subvention", "emi", "save", "benefit",
                       "limited period"],
    "colors":         ["color", "colour", "shade", "arctic", "metallic", "pearl",
                       "dual-tone", "lucent", "splendid", "sizzling", "exuberant",
                       "magma", "brave", "roof"],
}


# ══════════════════════════════════════════════════════════════════════════════
# PROMPTS — one per document type for best extraction quality
# ══════════════════════════════════════════════════════════════════════════════

_BASE_RULES = """
UNIVERSAL RULES (apply regardless of document type):
- Preserve all numbers exactly: ₹, km/l, km/kg, bhp, PS, Nm, mm, kg, cc, RPM, litres
- Keep model/variant names exact: LXi, VXi, ZXi, ZXi+, Alpha, Delta, Sigma, Zeta, S, V, VX
- Use "## SECTION NAME" for major section headings
- For any table or grid: output as pipe-separated rows — Header1 | Header2 | Header3
- For tick (✓/✔/●/Yes): write "Yes". For cross (✗/—/No/dash): write "No"
- Skip: page borders, background patterns, watermarks, pure decorative elements
- Skip: legal disclaimer fine print (starts with "reserves the right to change")
- Skip: repeated brand headers/footers that appear on every page
- If a page is purely a lifestyle photo with no text: write [VISUAL PAGE: one-line description]
- Return ONLY extracted text. No preamble, no explanation, no commentary.
"""

PROMPTS = {

"brochure": """You are extracting a CAR BROCHURE for an AI voice agent that answers customer calls.
Customers will ask: "What features does it have?", "Tell me about the engine", "What safety features?"

Extract every section completely:

## OVERVIEW / HIGHLIGHTS
- Extract the tagline, key selling points, and introductory paragraph verbatim

## FEATURES & TECHNOLOGY
- List every feature with its full description
- Include feature names shown as captions under images (e.g. "Electric Sunroof", "360 View Camera")
- For connectivity: mention Android Auto, Apple CarPlay, wireless/wired, voice assistant details

## ENGINE & PERFORMANCE
- Extract all engine variants (Petrol, Diesel, CNG, Hybrid)
- Mileage figures per variant — preserve exactly as shown even if in styled boxes
  Format: "Variant: X.XX km/l" e.g. "LXi MT: 17.80 km/l"

## EXTERIOR
- List exterior features: headlamp type, alloy wheels, body cladding, antenna, finish options

## INTERIOR
- List interior features: seat material, steering, AC type, ambient lighting, storage

## SAFETY
- List all safety features with counts: "6 Airbags (Front, Side, Curtain)"
- Include active safety: ESP, ABS, Hill Hold, ISOFIX, speed alert

## COLORS
- List every color option with dual-tone info and variant restrictions
  Format: "Color Name [Dual Tone: Yes/No] — Available in: ZXi, ZXi+"
""" + _BASE_RULES,


"pricing_sheet": """You are extracting a CAR PRICING SHEET for an AI voice agent that answers customer calls.
Customers will ask: "What is the price of ZXi?", "What's the on-road price?", "What's the EMI?"

Extract all pricing data with maximum precision:

## PRICING TABLE
- Output every variant and its price as: "Variant Name | Ex-Showroom | On-Road (if present)"
- Example: "Swift LXi MT | ₹6,49,000 | ₹7,12,500"
- Include ALL variants: petrol MT, petrol AT, CNG, diesel if present

## EMI & FINANCE OPTIONS
- Extract EMI schemes: "ZXi+ AT: ₹X,XXX/month for XX months at X% interest"
- Extract down payment options if shown
- Extract special finance schemes (0% EMI, subvention schemes)

## APPLICABLE CHARGES (if shown)
- Insurance, registration, handling charges, accessories package prices

## CITY / LOCATION (if specified)
- Note which city/state these prices apply to

## VALIDITY
- Extract offer validity period if mentioned: "Valid till: 31 March 2026"
""" + _BASE_RULES,


"feature_comparison": """You are extracting a CAR FEATURE COMPARISON DOCUMENT for an AI voice agent.
Customers will ask: "Does the VXi have a sunroof?", "Which variant has wireless Android Auto?"

This document has variant comparison tables — extract them completely and accurately:

## FEATURE TABLE FORMAT
Output each section as a table:
Section Name
Feature | LXi | VXi | ZXi | ZXi+   <- use actual variant names from document header
Feature1 | Yes | Yes | No | Yes
Feature2 | No | 17.78cm SmartPlay Studio | 17.78cm SmartPlay Pro | 22.86cm SmartPlay Pro+

- Preserve the ACTUAL value in cells (not just Yes/No when the cell has specific text)
- Example cells with real values: "Bi-Halogen", "Dual LED", "4 Speakers", "Manual", "Auto"
- Group by section exactly as in document: SAFETY, INFOTAINMENT, COMFORT AND CONVENIENCE,
  EXTERIORS, INTERIORS, COLOUR VARIANTS, etc.

## SPECIFICATION TABLE (if present)
- Extract dimensions, engine specs, transmission as "Spec: Value [per variant if different]"

## COLOR AVAILABILITY TABLE (if present)
- "Color | LXi | VXi | ZXi | ZXi+" with Yes/No
""" + _BASE_RULES,


"promotional_offer": """You are extracting a PROMOTIONAL OFFERS DOCUMENT for an AI voice agent.
Customers will ask: "What offers are available?", "How much discount?", "Any exchange bonus?"

Extract every offer with complete details:

## CURRENT OFFERS
For each offer extract:
- Offer type: Cash Discount / Exchange Bonus / Corporate Discount / Loyalty Bonus / Subvention
- Amount: ₹X,XXX or X%
- Applicable variants: "All variants" or specific ones
- Conditions: any eligibility criteria

Format:
"Cash Discount: ₹30,000 - Applicable on ZXi and ZXi+ - Valid till 31 March 2026"
"Exchange Bonus: ₹20,000 - On exchange of any old vehicle - All variants"

## EMI SCHEMES (if present)
- "0% EMI for 12 months on ZXi+ AT - Down payment: ₹1,50,000"
- "Low cost EMI: ₹X,XXX/month for XX months - Bank: HDFC/SBI/ICICI"

## TOTAL BENEFIT SUMMARY (if shown)
- "Total savings up to: ₹X,XXX on ZXi+"

## VALIDITY & TERMS
- Extract validity dates, stock conditions, dealership-specific notes
""" + _BASE_RULES,


"spec_sheet": """You are extracting a CAR SPECIFICATION SHEET for an AI voice agent.
Customers will ask: "What is the engine size?", "What's the mileage?", "Boot space?"

Extract all specifications completely:

## DIMENSIONS
- Length, Width, Height (unladen), Wheelbase, Ground Clearance, Boot Space, Seating Capacity
- Format: "Length: 3995 mm | Width: 1790 mm | Height: 1685 mm | Wheelbase: 2500 mm"

## ENGINE
- For each fuel type (Petrol/Diesel/CNG/Hybrid) extract:
  Engine Type | Capacity (cc) | Max Power (bhp/PS @ RPM) | Max Torque (Nm @ RPM) | Emission Norm

## FUEL EFFICIENCY
- Per variant and transmission: "LXi MT: 17.80 km/l | ZXi MT: 19.89 km/l | CNG: 25.51 km/kg"

## TRANSMISSION
- Available types: 5MT, 6MT, 6AT, AMT, CVT — which variants get which

## SUSPENSION & BRAKES
- Front and rear suspension type
- Front and rear brake type

## TYRES
- Size and type per variant

## FUEL TANK & OTHER
- Fuel tank capacity, CNG cylinder capacity (water equivalent)
""" + _BASE_RULES,


"warranty": """You are extracting a WARRANTY / SERVICE document for an AI voice agent.
Customers will ask: "How many years warranty?", "What's covered?", "Free service intervals?"

## WARRANTY COVERAGE
- Standard warranty: "X years or X,XX,XXX km whichever is earlier"
- Extended warranty options: duration, cost, coverage limit
- Powertrain warranty if separate
- Battery warranty (for hybrid/EV)

## FREE SERVICE SCHEDULE
- List each free service: "1st Service: 1,000 km or 1 month | 2nd Service: 10,000 km or 12 months"

## ANNUAL MAINTENANCE CONTRACT (AMC)
- Packages available, what's included, pricing if shown

## ROADSIDE ASSISTANCE
- Coverage area, what's included, how to contact

## WHAT'S COVERED / NOT COVERED (if shown)
- Briefly list major inclusions and exclusions
""" + _BASE_RULES,


"general": """You are extracting a car dealership document for an AI voice agent that answers customer calls.
The document may contain any combination of: brochure content, pricing, features, specs, offers.

Extract ALL useful content that a customer might ask about:
- Any pricing or variant information
- Any feature lists or technology descriptions
- Any engine, mileage, or specification data
- Any promotional offers or discounts
- Any safety features or ratings
- Any color or variant options
- Any warranty or service information

Use "## SECTION NAME" for each logical section you identify.
For any table or grid, use pipe-separated format: Col1 | Col2 | Col3
For mileage boxes or spec callouts, extract each value with its label.
""" + _BASE_RULES,

}


# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENT TYPE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def detect_document_type(document_type_field: str, filename: str) -> str:
    """
    Determine which extraction prompt to use.

    Priority:
    1. document_type field set during upload (user explicitly chose)
    2. Filename keyword detection
    3. Default to "brochure" (most common)
    """
    type_map = {
        "brochure":           "brochure",
        "pricing_sheet":      "pricing_sheet",
        "feature_comparison": "feature_comparison",
        "promotional_offer":  "promotional_offer",
        "spec_sheet":         "spec_sheet",
        "other":              "general",
    }
    if document_type_field in type_map:
        mapped = type_map[document_type_field]
        if mapped != "general":
            logger.info(f"Document type from upload field: {mapped}")
            return mapped

    fname = filename.lower()
    if any(kw in fname for kw in ["price", "pricing", "rate", "cost"]):
        return "pricing_sheet"
    if any(kw in fname for kw in ["feature", "comparison", "spec", "specification"]):
        return "feature_comparison"
    if any(kw in fname for kw in ["offer", "discount", "promo", "scheme", "festive"]):
        return "promotional_offer"
    if any(kw in fname for kw in ["warranty", "service", "amc"]):
        return "warranty"
    if any(kw in fname for kw in ["brochure", "catalogue", "catalog"]):
        return "brochure"

    return "brochure"


# ══════════════════════════════════════════════════════════════════════════════
# OPENAI CLIENT
# ══════════════════════════════════════════════════════════════════════════════

def _get_openai_client():
    """
    Initialise and return an OpenAI client.

    Install: pip install openai --break-system-packages
    .env:    OPENAI_API_KEY=sk-...

    Raises:
        RuntimeError if key not set or SDK not installed.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY not set.\n"
            "Get a key at https://platform.openai.com/api-keys\n"
            "Then add to .env: OPENAI_API_KEY=sk-..."
        )
    try:
        from openai import OpenAI  # type: ignore[import]
        return OpenAI(api_key=OPENAI_API_KEY)
    except ImportError:
        raise RuntimeError(
            "openai SDK not installed.\n"
            "Run: pip install openai --break-system-packages"
        )


# ══════════════════════════════════════════════════════════════════════════════
# RATE LIMITING
# ══════════════════════════════════════════════════════════════════════════════

def _rate_limit_openai() -> None:
    """
    Enforce a minimum gap between consecutive OpenAI API calls.
    OpenAI tier-1 allows 500 RPM for gpt-4o-mini, so 0.5s is very conservative.
    """
    global _last_openai_call_time
    now = time.monotonic()
    elapsed = now - _last_openai_call_time
    if elapsed < OPENAI_MIN_INTERVAL_SECONDS:
        sleep_for = OPENAI_MIN_INTERVAL_SECONDS - elapsed
        logger.debug(f"Rate limiter: sleeping {sleep_for:.2f}s before OpenAI call")
        time.sleep(sleep_for)
    _last_openai_call_time = time.monotonic()


# ══════════════════════════════════════════════════════════════════════════════
# CORE EXTRACTION — image bytes → OpenAI Vision
# ══════════════════════════════════════════════════════════════════════════════

def _extract_from_image_bytes(
    image_bytes: bytes,
    mime_type: str,
    client,
    prompt: str,
    page_label: str = "page",
    max_retries: int = 3,
) -> str:
    """
    Send image bytes + prompt to OpenAI Vision and return extracted text.

    The image is base64-encoded and sent inline — no separate upload step.

    Features:
    - In-process MD5 cache: identical page images are never sent twice
    - Proactive rate limiting before every call
    - Exponential backoff on 429 rate limit errors
    - Returns empty string on final failure (caller handles gracefully)

    Args:
        image_bytes: Raw PNG/JPEG bytes of the page.
        mime_type:   "image/png" or "image/jpeg".
        client:      openai.OpenAI instance from _get_openai_client().
        prompt:      Type-specific extraction prompt.
        page_label:  Human-readable label for log messages.
        max_retries: Attempts before giving up on this page.

    Returns:
        Extracted text string, or "" on failure.
    """
    # ── Cache check ────────────────────────────────────────────────────────────
    cache_key = hashlib.md5(image_bytes).hexdigest()
    if cache_key in _page_cache:
        logger.info(f"Cache hit: {page_label} — skipping OpenAI call")
        return _page_cache[cache_key]

    # Base64 encode image for inline sending
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    data_url  = f"data:{mime_type};base64,{b64_image}"

    for attempt in range(1, max_retries + 1):
        try:
            _rate_limit_openai()

            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url":    data_url,
                                    "detail": "high",  # use "low" for simple cover pages
                                },
                            },
                        ],
                    }
                ],
                max_tokens=2000,
                temperature=0,  # deterministic for data extraction
            )

            text = (response.choices[0].message.content or "").strip()
            logger.info(f"OpenAI ✓ {page_label} → {len(text)} chars")
            _page_cache[cache_key] = text
            return text

        except Exception as e:
            err_str = str(e)

            # Auth errors — no point retrying
            is_auth = (
                "401" in err_str
                or "authentication" in err_str.lower()
                or "api_key" in err_str.lower()
                or "Incorrect API key" in err_str
            )
            if is_auth:
                logger.error(
                    f"OpenAI auth failed — check OPENAI_API_KEY in .env\nError: {e}"
                )
                return ""

            # Rate limit — read retry-after from error, wait exactly that long
            is_rate_limit = "429" in err_str or "rate_limit" in err_str.lower()
            if is_rate_limit and attempt < max_retries:
                # Try to extract the actual retry-after value from the error message
                import re as _re
                retry_match = _re.search(r"retry.{0,20}?(\d+)\s*s", err_str, _re.IGNORECASE)
                wait = int(retry_match.group(1)) if retry_match else (10 * attempt)
                wait = min(wait + 2, 65)  # +2s buffer, cap at 65s
                logger.warning(
                    f"Rate limit on {page_label} "
                    f"(attempt {attempt}/{max_retries}). Waiting {wait}s..."
                )
                time.sleep(wait)
                continue  # retry immediately after wait

            # Other errors — log and retry with short backoff
            if attempt < max_retries:
                wait = 3 * attempt
                logger.warning(
                    f"OpenAI error on {page_label} "
                    f"(attempt {attempt}/{max_retries}): {e}. Retrying in {wait}s..."
                )
                time.sleep(wait)
            else:
                logger.warning(
                    f"OpenAI failed on {page_label} after {max_retries} attempts: {e}"
                )
                return ""

    return ""


# ══════════════════════════════════════════════════════════════════════════════
# PAGE TEXT QUALITY ASSESSMENT
# ══════════════════════════════════════════════════════════════════════════════

def _assess_page_text(raw_text: str) -> Tuple[bool, int, str]:
    """
    Decide whether PyMuPDF-extracted page text is rich enough to use directly.

    Returns:
        (is_sufficient, char_count, reason_string)

    A page is text-sufficient when it has >= MIN_TEXT_THRESHOLD chars AND
    has more than 2 tokens (not just a page number or logo word).
    Pages that fail are forwarded to OpenAI Vision.
    """
    if not raw_text:
        return False, 0, "empty"

    stripped   = raw_text.strip()
    char_count = len(stripped)

    if char_count < MIN_TEXT_THRESHOLD:
        return False, char_count, f"too_short ({char_count} chars < {MIN_TEXT_THRESHOLD})"

    tokens = stripped.split()
    if len(tokens) <= 2:
        return False, char_count, f"only {len(tokens)} token(s) — likely logo/page-number"

    return True, char_count, "ok"


# ══════════════════════════════════════════════════════════════════════════════
# PDF EXTRACTION — PyMuPDF-first, OpenAI Vision only for image/scanned pages
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_from_pdf(file_path: str, doc_type: str = "brochure") -> str:
    """
    PIPELINE — OpenAI Vision PRIMARY, PyMuPDF FALLBACK per page.

    Per-page logic:
      1. Render page to PNG image (PyMuPDF renderer — no text extraction yet)
      2. Send PNG → OpenAI Vision with type-specific structured prompt
      3. If OpenAI returns >= 30 chars  → use Vision output (best quality)
         If OpenAI fails or returns < 30 chars:
           a. Try PyMuPDF text extraction as fallback
           b. If PyMuPDF also empty → mark as visual-only page

    Why Vision for every page (not just image pages):
      - Car brochures have multi-column layouts PyMuPDF linearises incorrectly
      - Feature comparison tables (LXi/VXi/ZXi/ZXi+) — PyMuPDF merges cells
      - Mileage callout boxes — PyMuPDF misses them entirely on styled pages
      - Consistent output format across all pages → cleaner chunks

    Args:
        file_path : Absolute path to the PDF.
        doc_type  : Key into PROMPTS dict for type-specific extraction.

    Returns:
        Concatenated text from all pages with [Page N] markers.
    """
    try:
        import fitz  # PyMuPDF — used for rendering pages to images
    except ImportError:
        raise RuntimeError(
            "PyMuPDF not installed. Run: pip install pymupdf --break-system-packages"
        )

    client  = _get_openai_client()
    prompt  = PROMPTS.get(doc_type, PROMPTS["general"])

    pdf_doc       = fitz.open(file_path)
    total_pages   = len(pdf_doc)  # type: ignore[arg-type]
    process_pages = min(total_pages, MAX_PAGES)
    page_texts: List[str] = []

    stats = {"openai": 0, "pymupdf_fallback": 0, "visual_only": 0}

    logger.info(
        f"PDF: '{file_path}' | {process_pages}/{total_pages} pages | "
        f"type={doc_type} | strategy=openai-vision-primary"
    )

    for page_num in range(process_pages):
        page  = pdf_doc[page_num]
        label = f"page {page_num + 1}/{process_pages}"

        # ── Step 1: Render page → PNG (used by OpenAI Vision) ─────────────────
        mat       = fitz.Matrix(PAGE_DPI / 72, PAGE_DPI / 72)  # type: ignore[attr-defined]
        pix       = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)  # type: ignore[attr-defined]
        img_bytes = pix.tobytes("png")

        # ── Step 2: OpenAI Vision — primary extraction ────────────────────────
        openai_text = _extract_from_image_bytes(
            img_bytes, "image/png", client, prompt, label
        )

        if openai_text and len(openai_text.strip()) > 30:
            # ── Path A: OpenAI succeeded ──────────────────────────────────────
            page_texts.append(f"[Page {page_num + 1}]\n{openai_text}")
            logger.info(f"✅ OpenAI Vision: {label} ({len(openai_text)} chars)")
            stats["openai"] += 1

        else:
            # ── Path B: OpenAI failed → PyMuPDF fallback ──────────────────────
            logger.warning(
                f"OpenAI low/no output for {label} — trying PyMuPDF fallback"
            )
            pymupdf_text = page.get_text("text").strip()  # type: ignore[attr-defined]

            if pymupdf_text and len(pymupdf_text) >= MIN_TEXT_THRESHOLD:
                page_texts.append(
                    f"[Page {page_num + 1}] [pymupdf-fallback]\n{pymupdf_text}"
                )
                logger.warning(f"↩ PyMuPDF fallback: {label} ({len(pymupdf_text)} chars)")
                stats["pymupdf_fallback"] += 1

            else:
                # Truly visual page — cover photo, decorative page etc.
                page_texts.append(f"[Page {page_num + 1}] [VISUAL — no text]")
                logger.info(f"○ Visual-only: {label}")
                stats["visual_only"] += 1

    pdf_doc.close()

    if total_pages > MAX_PAGES:
        page_texts.append(
            f"[Note: Document has {total_pages} pages. "
            f"Only first {MAX_PAGES} were processed.]"
        )

    logger.info(
        f"✓ Extraction complete | "
        f"OpenAI Vision: {stats['openai']} pages | "
        f"PyMuPDF fallback: {stats['pymupdf_fallback']} pages | "
        f"Visual-only: {stats['visual_only']} pages"
    )

    return "\n\n".join(page_texts)


# ══════════════════════════════════════════════════════════════════════════════
# DOCX EXTRACTION — text via python-docx + embedded images via OpenAI Vision
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_from_docx(file_path: str, doc_type: str = "brochure") -> str:
    """
    Extract DOCX:
      - Text paragraphs and tables via python-docx (no API call)
      - Embedded images sent to OpenAI Vision
    """
    try:
        from docx import Document as DocxDocument
    except ImportError:
        raise RuntimeError(
            "python-docx not installed. "
            "Run: pip install python-docx --break-system-packages"
        )

    client = _get_openai_client()
    prompt = PROMPTS.get(doc_type, PROMPTS["general"])
    doc    = DocxDocument(file_path)
    parts: List[str] = []

    # Text paragraphs
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = (para.style.name or "") if para.style else ""
        if style_name.startswith("Heading"):
            level  = style_name.replace("Heading", "").strip()
            prefix = "##" if level in ("1", "2", "") else "###"
            parts.append(f"\n{prefix} {text}\n")
        else:
            parts.append(text)

    # Tables — preserve structure as pipe-separated rows
    for table in doc.tables:
        rows: List[str] = []
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            deduped: List[str] = []
            prev = None
            for c in cells:
                if c != prev:
                    deduped.append(c)
                prev = c
            if any(deduped):
                rows.append(" | ".join(deduped))
        if rows:
            parts.append("\n[TABLE]\n" + "\n".join(rows) + "\n[/TABLE]")

    # Embedded images → OpenAI Vision
    image_count = 0
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            try:
                image_data = rel.target_part.blob
                mime       = "image/png" if image_data[:4] == b'\x89PNG' else "image/jpeg"
                image_count += 1
                label       = f"embedded image {image_count}"
                img_text    = _extract_from_image_bytes(
                    image_data, mime, client, prompt, label
                )
                if img_text and "[VISUAL PAGE" not in img_text and len(img_text) > 20:
                    parts.append(f"\n[From {label}]\n{img_text}")
            except Exception as e:
                logger.warning(f"Could not extract DOCX image: {e}")

    return "\n\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE EXTRACTION — direct OpenAI Vision
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_from_image(file_path: str, doc_type: str = "brochure") -> str:
    """Send an uploaded image file directly to OpenAI Vision."""
    client = _get_openai_client()
    prompt = PROMPTS.get(doc_type, PROMPTS["general"])

    with open(file_path, "rb") as f:
        image_bytes = f.read()

    ext      = os.path.splitext(file_path)[1].lower()
    mime_map = {
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(ext, "image/jpeg")

    text = _extract_from_image_bytes(
        image_bytes, mime_type, client, prompt, "uploaded image"
    )
    if not text:
        raise ValueError("OpenAI Vision could not extract any text from this image")
    return text


# ══════════════════════════════════════════════════════════════════════════════
# TEXT CLEANING
# ══════════════════════════════════════════════════════════════════════════════

def clean_extracted_text(raw_text: str) -> str:
    """Normalise extracted text for chunking."""
    if not raw_text:
        return ""

    # Remove page markers added by our pipeline
    text = re.sub(r'\[Page \d+(/\d+)?\]\s*(\[.*?\])?\n?', '', raw_text)

    # Collapse 3+ blank lines -> 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove standalone page numbers
    text = re.sub(r'^\s*\d{1,3}\s*$', '', text, flags=re.MULTILINE)

    # Remove "Page X of Y"
    text = re.sub(r'Page\s+\d+\s+of\s+\d+', '', text, flags=re.IGNORECASE)

    # Collapse multiple spaces (preserve newlines)
    text = re.sub(r'[ \t]{2,}', ' ', text)

    # Strip non-printable chars (keep unicode, tabs, newlines)
    text = re.sub(r'[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]', '', text)

    return text.strip()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════

def classify_section(text: str) -> str:
    """
    Classify a chunk into a section type.
    Checks ## headers first (strong signal), then falls back to keyword scoring.
    """
    header_match = re.search(r'##\s+([\w][\w\s&+/-]*)', text)
    if header_match:
        header = header_match.group(1).lower()
        if any(k in header for k in ["price", "variant", "cost", "rate"]):
            return "pricing"
        if any(k in header for k in ["spec", "engine", "dimension", "performance", "fuel", "technical"]):
            return "specifications"
        if any(k in header for k in ["safety", "airbag", "esp"]):
            return "safety"
        if any(k in header for k in ["feature", "technology", "connect", "infotainment", "interior", "exterior"]):
            return "features"
        if any(k in header for k in ["offer", "discount", "promo", "scheme", "emi", "benefit"]):
            return "offers"
        if any(k in header for k in ["warranty", "service", "amc", "maintenance"]):
            return "warranty"
        if any(k in header for k in ["color", "colour"]):
            return "colors"
        if any(k in header for k in ["overview", "about", "highlight", "introduction"]):
            return "overview"

    text_lower = text.lower()
    scores: dict = {}
    for section, keywords in SECTION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[section] = score

    return max(scores, key=lambda k: scores[k]) if scores else "general"


# ══════════════════════════════════════════════════════════════════════════════
# CHUNKING
# ══════════════════════════════════════════════════════════════════════════════

def split_into_chunks(text: str) -> List[Tuple[int, str]]:
    """Split on ## section markers, then paragraphs, then sentences."""
    chunks: List[str] = []

    if "## " in text:
        sections = re.split(r'\n(?=## )', text)
        for section in sections:
            section = section.strip()
            if not section:
                continue
            if len(section) <= CHUNK_SIZE * 1.5:
                chunks.append(section)
            else:
                chunks.extend(_split_by_paragraphs(section))
    else:
        chunks = _split_by_paragraphs(text)

    return [(i, c.strip()) for i, c in enumerate(chunks) if len(c.strip()) >= MIN_CHUNK_CHARS]


def _split_by_paragraphs(text: str) -> List[str]:
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) < CHUNK_SIZE:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            if len(para) > CHUNK_SIZE:
                sub = _split_by_sentences(para)
                chunks.extend(sub[:-1])
                current = sub[-1] if sub else ""
            else:
                current = para
    if current:
        chunks.append(current)
    return chunks


def _split_by_sentences(text: str) -> List[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks: List[str] = []
    current = ""
    for s in sentences:
        if len(current) + len(s) < CHUNK_SIZE:
            current = (current + " " + s).strip()
        else:
            if current:
                chunks.append(current)
            current = s
    if current:
        chunks.append(current)
    return chunks


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PROCESSING FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def process_document(document_id: str, db: Session) -> dict:
    """
    Full multimodal processing pipeline.

    1. Detect document type -> select appropriate prompt
    2. Extract text:
         PDF  -> PyMuPDF-first (OpenAI Vision only for image/scanned pages)
         DOCX -> python-docx text + OpenAI Vision for embedded images
         IMG  -> OpenAI Vision directly
    3. Clean -> chunk -> classify sections
    4. Save chunks -> update document status
    """
    doc = db.query(Document).filter(Document.document_id == document_id).first()
    if not doc:
        return {"error": "Document not found"}

    doc.processing_status = "processing"  # type: ignore[assignment]
    doc.updated_at        = datetime.utcnow()  # type: ignore[assignment]
    db.commit()

    extraction_method = "unknown"

    try:
        file_path = str(doc.file_path)
        file_type = str(doc.file_type)
        doc_type  = detect_document_type(
            str(doc.document_type or "brochure"),
            str(doc.filename or "")
        )

        logger.info(
            f"Processing: '{doc.filename}' | "
            f"file_type={file_type} | doc_type={doc_type}"
        )

        # ── Extract ────────────────────────────────────────────────────────────
        if file_type == "pdf":
            raw_text          = extract_text_from_pdf(file_path, doc_type)
            extraction_method = (
                f"openai-vision/{OPENAI_MODEL} (primary) + pymupdf-fallback"
            )

        elif file_type == "docx":
            raw_text          = extract_text_from_docx(file_path, doc_type)
            extraction_method = f"python-docx + openai-vision/{OPENAI_MODEL}"

        elif file_type == "image":
            raw_text          = extract_text_from_image(file_path, doc_type)
            extraction_method = f"openai-vision/{OPENAI_MODEL}"

        else:
            raise ValueError(f"Unsupported file type: {file_type}")

        # ── Clean ──────────────────────────────────────────────────────────────
        clean_text = clean_extracted_text(raw_text)
        if not clean_text:
            raise ValueError("No readable text could be extracted from this document")

        doc.extracted_text = clean_text  # type: ignore[assignment]

        # ── Chunk ──────────────────────────────────────────────────────────────
        chunk_tuples = split_into_chunks(clean_text)
        if not chunk_tuples:
            raise ValueError("Document could not be split into meaningful chunks")

        # ── Delete old chunks (reprocessing) ──────────────────────────────────
        db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).delete()

        # ── Save chunks ────────────────────────────────────────────────────────
        for idx, chunk_text in chunk_tuples:
            chunk = DocumentChunk(
                chunk_id      = uuid.uuid4(),
                document_id   = doc.document_id,
                dealership_id = doc.dealership_id,
                car_model_id  = doc.car_model_id,
                chunk_index   = idx,
                chunk_text    = chunk_text,
                section_type  = classify_section(chunk_text),
                char_count    = len(chunk_text),
            )
            db.add(chunk)

        # ── Finalise ───────────────────────────────────────────────────────────
        doc.processing_status = "completed"        # type: ignore[assignment]
        doc.chunk_count       = len(chunk_tuples)  # type: ignore[assignment]
        doc.updated_at        = datetime.utcnow()  # type: ignore[assignment]
        db.commit()

        logger.info(
            f"✓ '{doc.filename}': {len(chunk_tuples)} chunks | {extraction_method}"
        )

        return {
            "document_id":       str(document_id),
            "processing_status": "completed",
            "chunk_count":       len(chunk_tuples),
            "doc_type_detected": doc_type,
            "extraction_method": extraction_method,
            "message": (
                f"Extracted {len(chunk_tuples)} chunks from '{doc.filename}' "
                f"[{doc_type}] via {extraction_method}"
            ),
        }

    except Exception as e:
        db.rollback()
        doc.processing_status = "failed"          # type: ignore[assignment]
        doc.processing_error  = str(e)            # type: ignore[assignment]
        doc.updated_at        = datetime.utcnow() # type: ignore[assignment]
        db.commit()
        logger.error(f"✗ '{doc.filename}': {e}")
        return {
            "document_id":       str(document_id),
            "processing_status": "failed",
            "chunk_count":       0,
            "extraction_method": extraction_method,
            "message":           f"Processing failed: {str(e)}",
        }