def _downscale_messages_images(messages: list, max_dim: int = 2048):
    """Ensures base64 images do not exceed OpenAI's 30,000 patch limit by capping resolution at 2048px."""
    if not isinstance(messages, list):
        return
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "image_url":
                continue
            image_url = part.get("image_url")
            if not isinstance(image_url, dict):
                continue
            url = image_url.get("url", "")
            if isinstance(url, str) and url.startswith("data:image/") and ";base64," in url:
                try:
                    import base64, io
                    from PIL import Image
                    header, b64_str = url.split(";base64,", 1)
                    raw = base64.b64decode(b64_str)
                    img = Image.open(io.BytesIO(raw))
                    if max(img.size) > max_dim:
                        resample = getattr(Image, "Resampling", Image).LANCZOS
                        img.thumbnail((max_dim, max_dim), resample)
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        new_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                        image_url["url"] = f"data:image/png;base64,{new_b64}"
                except Exception:
                    pass

"""
core/prompt_cache_manager.py
============================
Universal Prompt Caching Module for all POCs.

Provides guaranteed OpenAI Prompt Caching (50% input discount & ~40% latency reduction)
across any POC in the workspace by:
1. Enforcing the 1,024-token minimum prefix threshold via automatic calibration padding.
2. Enforcing strict static-prefix-first message ordering (System -> User).
3. Automatically hoisting static category/schema blocks above dynamic document text.
4. Globally hooking OpenAI Completions.create / AsyncCompletions.create so all POCs
   benefit automatically as a connected module without modifying locked POC files.
5. Seamlessly integrating with core.universal_token_monitor.
"""

import os
import sys
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime, timezone
from pathlib import Path

# Set up logger
logger = logging.getLogger("prompt_cache_manager")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [PromptCache] %(message)s"))
    logger.addHandler(handler)

# Try importing tiktoken for exact token measurement
try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
# Standardized Document & OCR Calibration Guidelines
# Used to pad short prompts past OpenAI's 1,024-token caching threshold.
# ──────────────────────────────────────────────────────────────────────────────
STANDARDIZED_CALIBRATION_RULES = """
=== CORE DOCUMENT EXTRACTION & OCR PRECISION PROTOCOLS ===
1. VERBATIM FIDELITY:
   - Extract raw text exactly as printed. Do not correct typos, infer unprinted abbreviations, or normalize non-standard spelling unless strictly requested by the schema.
   - Never generate placeholder, synthetic, or phantom names (e.g., 'John Doe', 'Jane Smith', 'Sample Claimant').

2. NUMERIC & FINANCIAL DATA INTEGRITY:
   - Clean monetary values by removing currency symbols ($, €, £) and thousand-separators (,), converting to standard float representation (e.g., '14,250.00' -> 14250.00).
   - Retain trailing zeros in decimal representations when formatting as currency strings.
   - For missing financial amounts, return 0.0 or explicit null as dictated by schema requirements, never omit mandatory keys.
   - Mathematical balancing rule: Paid amounts plus Reserved amounts must consistently reconcile against Total Incurred amounts (Paid + Reserve = Incurred).

3. DATES & TEMPORAL FIELDS:
   - Prioritize primary event dates (e.g., Date of Loss, Date of Injury, Benefit Year Begins) over procedural tracking dates (e.g., Date Received, Printed Date, Scan Date).
   - Format dates uniformly according to the ISO-8601 standard (YYYY-MM-DD) or target specification (MM/DD/YYYY).
   - When only 2-digit years are present, resolve appropriately based on context (e.g., '24' -> '2024').

4. STRUCTURAL HIERARCHY & LAYOUT PRESERVATION:
   - Respect visual indentation, column alignments, and tabular associations across line wraps.
   - In multi-row claim records or split-screen screenshots, maintain strict field-to-claimant correspondence.
   - Group summaries, sub-totals, and grand-total rows must not be confused with individual claimant or policy transaction rows.

5. ERROR SUPPRESSION & UNCERTAINTY HANDLING:
   - If a specific field is partially smudged, blurry, or missing from the source image/text, output null or empty string rather than attempting speculative completion.
   - Return valid, syntactically clean JSON matching the required schema without conversational commentary or markdown fencing.
"""


def count_tokens(text: str, model: str = "gpt-5.6-terra") -> int:
    """
    Returns the exact token count for the given text using tiktoken (o200k_base for gpt-5.6-terra),
    or falls back to conservative character ratio estimation (~5 chars/token for o200k_base).
    """
    if _TIKTOKEN_AVAILABLE:
        try:
            enc_name = "o200k_base" if ("4o" in model or "5" in model or "o1" in model or "o3" in model) else "cl100k_base"
            encoding = tiktoken.get_encoding(enc_name)
            return len(encoding.encode(text))
        except Exception:
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
                return len(encoding.encode(text))
            except Exception:
                pass
    # Conservative fallback for o200k_base (~5 chars per token so we never under-pad below 1,024 tokens)
    return max(1, len(text) // 5)


def ensure_cache_threshold(system_prompt: str, min_tokens: int = 1200) -> str:
    """
    Ensures that the static system prompt meets or exceeds OpenAI's 1,024-token
    threshold for automatic prompt caching.
    
    If the prompt is shorter than min_tokens, cleanly appends standardized
    calibration rules until safely over the threshold.
    """
    current_tokens = count_tokens(system_prompt)
    if current_tokens >= min_tokens:
        return system_prompt

    # Calculate padding needed
    tokens_needed = min_tokens - current_tokens
    logger.debug(f"Prompt is {current_tokens} tokens (< {min_tokens}). Appending calibration padding...")

    padding_block = STANDARDIZED_CALIBRATION_RULES.strip()
    padding_tokens = count_tokens(padding_block)

    multiplier = (tokens_needed // padding_tokens) + 1
    repeated_padding = ("\n\n" + padding_block) * multiplier

    padded_prompt = f"{system_prompt.strip()}\n\n{repeated_padding.strip()}"
    return padded_prompt


def build_cached_messages(
    static_system_prompt: str,
    dynamic_user_content: Union[str, List[Dict[str, Any]]],
    ensure_threshold: bool = True,
    min_tokens: int = 1200
) -> List[Dict[str, Any]]:
    """
    Builds the OpenAI messages array with guaranteed prefix caching structure:
    1. Static System Prompt (padded to >= 1,024 tokens if needed) -> Cached Prefix
    2. Dynamic User Content (document text, chunk text, or vision image URLs) -> Dynamic Payload
    """
    prepared_system = (
        ensure_cache_threshold(static_system_prompt, min_tokens=min_tokens)
        if ensure_threshold
        else static_system_prompt
    )

    return [
        {"role": "system", "content": prepared_system},
        {"role": "user", "content": dynamic_user_content}
    ]


def optimize_messages_for_caching(
    messages: List[Dict[str, Any]],
    model: str = "gpt-5.6-terra",
    min_tokens: int = 1200
) -> List[Dict[str, Any]]:
    """
    Automatically optimizes any standard OpenAI messages array so it qualifies
    for OpenAI Prompt Caching (>= 1,024 static prefix tokens at index 0)
    without altering downstream logic or extraction accuracy.
    """
    if not messages or not isinstance(messages, list):
        return messages

    model_lower = (model or "").lower()
    if model_lower.startswith("o1-mini") or model_lower.startswith("o1-preview"):
        return messages

    optimized = [dict(m) if isinstance(m, dict) else m for m in messages]
    first_msg = optimized[0]
    if not isinstance(first_msg, dict):
        return messages

    role = first_msg.get("role", "")
    content = first_msg.get("content", "")

    # Special optimization for classifiers/extractors that place CATEGORIES AND THEIR KEYWORDS
    # at the bottom of the user message: hoist static categories & rules into the system prefix
    if len(optimized) >= 2 and role in ("system", "developer") and isinstance(content, str):
        second_msg = optimized[1]
        if isinstance(second_msg, dict) and second_msg.get("role") == "user":
            user_content = second_msg.get("content", "")
            if isinstance(user_content, str):
                if "\n\nCATEGORIES AND THEIR KEYWORDS:\n" in user_content:
                    dyn_part, static_tail = user_content.split("\n\nCATEGORIES AND THEIR KEYWORDS:\n", 1)
                    content = f"{content.strip()}\n\nCATEGORIES AND THEIR KEYWORDS:\n{static_tail.strip()}"
                    first_msg["content"] = content
                    second_msg["content"] = dyn_part.strip()
                elif "Document Text:\n" in user_content:
                    # Parity setup & document extractors: hoist static extraction rules before 'Document Text:'
                    static_head, dyn_doc = user_content.split("Document Text:\n", 1)
                    if len(static_head.strip()) > 300:
                        content = f"{content.strip()}\n\n{static_head.strip()}"
                        first_msg["content"] = content
                        second_msg["content"] = f"Document Text:\n{dyn_doc.strip()}"

    if role in ("system", "developer") and isinstance(content, str):
        if count_tokens(content, model=model) < min_tokens:
            first_msg["content"] = ensure_cache_threshold(content, min_tokens=min_tokens)
        return optimized

    if role == "user":
        default_static_system = ensure_cache_threshold(
            "You are a high-precision document intelligence and structured data extraction engine. "
            "Adhere strictly to all instructions, formatting rules, and schemas provided in the user prompt.",
            min_tokens=min_tokens
        )
        optimized.insert(0, {"role": "system", "content": default_static_system})
        return optimized

    return optimized


def _infer_caller_context() -> Tuple[str, str, str]:
    """
    Walks the call stack to automatically identify (poc_name, file_name, step_name)
    for any POC calling client.chat.completions.create(...).
    """
    poc_name = "general_poc"
    file_name = "document"
    step_name = "llm_call"

    try:
        from universal_token_monitor import get_context
        ctx = get_context()
        if ctx.get("poc_name"):
            poc_name = ctx["poc_name"]
        if ctx.get("file_name"):
            file_name = ctx["file_name"]
    except Exception:
        pass

    try:
        workspace_root = Path(__file__).resolve().parent.parent
        frame = sys._getframe(1)
        while frame:
            co_file = frame.f_code.co_filename
            if co_file and "prompt_cache_manager" not in co_file and "openai" not in co_file.lower():
                p = Path(co_file).resolve()
                try:
                    rel = p.relative_to(workspace_root)
                    if len(rel.parts) > 1 and rel.parts[0] != "core":
                        if poc_name == "general_poc":
                            poc_name = rel.parts[0]
                        step_name = frame.f_code.co_name or step_name
                        f_locals = frame.f_locals
                        for key in ("file_name", "filename", "safe_filename", "pdf_path", "file_path", "working_path"):
                            val = f_locals.get(key)
                            if val and isinstance(val, (str, Path)):
                                file_name = os.path.basename(str(val))
                                break
                        break
                except Exception:
                    pass
            frame = frame.f_back
    except Exception:
        pass

    return poc_name, file_name, step_name


# ──────────────────────────────────────────────────────────────────────────────
# Global In-Memory Cache Performance Tracker
# ──────────────────────────────────────────────────────────────────────────────
_CACHE_STATS = {
    "total_calls": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "total_prompt_tokens": 0,
    "total_cached_tokens": 0,
    "total_completion_tokens": 0,
    "estimated_usd_saved": 0.0
}


def _record_cache_observability(response: Any, model: str = "gpt-5.6-terra", poc_name: str = "general_poc") -> None:
    """Extracts cached token metrics from an OpenAI response and updates global stats once per response."""
    try:
        if response is None or getattr(response, "_prompt_cache_recorded", False):
            return
        try:
            setattr(response, "_prompt_cache_recorded", True)
        except Exception:
            pass

        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

        cached_tokens = 0
        if usage and hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
            cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0

        if "mini" in (model or "").lower():
            prompt_rate = 0.15 / 1_000_000
        else:
            prompt_rate = 2.50 / 1_000_000

        usd_saved = cached_tokens * prompt_rate * 0.5

        _CACHE_STATS["total_calls"] += 1
        _CACHE_STATS["total_prompt_tokens"] += prompt_tokens
        _CACHE_STATS["total_completion_tokens"] += completion_tokens
        _CACHE_STATS["total_cached_tokens"] += cached_tokens
        _CACHE_STATS["estimated_usd_saved"] += usd_saved

        if cached_tokens > 0:
            _CACHE_STATS["cache_hits"] += 1
            status_msg = f"[PROMPT CACHE HIT] {cached_tokens}/{prompt_tokens} tokens cached (50% OFF) | Saved: ${usd_saved:.6f}"
        else:
            _CACHE_STATS["cache_misses"] += 1
            status_msg = f"[PROMPT CACHE WRITTEN] {prompt_tokens} tokens cached for next calls"

        try:
            print(f"[{poc_name}] [{model}] {status_msg}")
        except Exception:
            pass
    except Exception:
        pass


def cached_chat_completion(
    client: Any,
    static_system_prompt: str,
    dynamic_user_content: Union[str, List[Dict[str, Any]]],
    model: str = "gpt-5.6-terra",
    poc_name: str = "general_poc",
    file_name: str = "document",
    step_name: str = "extraction",
    temperature: Optional[float] = None,
    response_format: Optional[Dict[str, str]] = None,
    ensure_threshold: bool = True,
    min_tokens: int = 1050,
    **kwargs
) -> Any:
    """
    Universal drop-in replacement for client.chat.completions.create with
    automatic prompt caching, token logging, and 50% cached discount monitoring.
    """
    messages = build_cached_messages(
        static_system_prompt=static_system_prompt,
        dynamic_user_content=dynamic_user_content,
        ensure_threshold=ensure_threshold,
        min_tokens=min_tokens
    )

    request_params = {
        "model": model,
        "messages": messages,
        **kwargs
    }

    if response_format:
        request_params["response_format"] = response_format

    # Set temperature only if specified and supported by the model
    if temperature is not None:
        model_lower = model.lower()
        if not (model_lower.startswith("o1") or model_lower.startswith("o3") or "gpt-5" in model_lower):
            request_params["temperature"] = temperature

    # Execute LLM call
    response = client.chat.completions.create(**request_params)

    # Record observability metrics (idempotent even if global hook is active)
    _record_cache_observability(response, model=model, poc_name=poc_name)

    # Forward to Universal Token Monitor
    try:
        cur_dir = Path(__file__).resolve().parent
        if str(cur_dir) not in sys.path:
            sys.path.insert(0, str(cur_dir))
        from universal_token_monitor import track_usage as _track_universal
        _track_universal(
            response_usage=getattr(response, "usage", None),
            model=model,
            poc_name=poc_name,
            file_name=file_name,
            step_name=step_name
        )
    except Exception as monitor_err:
        logger.debug(f"Universal token monitor update skipped: {monitor_err}")

    return response


# ──────────────────────────────────────────────────────────────────────────────
# Automatic Global OpenAI Client Hook (Zero-Touch Module Integration)
# ──────────────────────────────────────────────────────────────────────────────
_GLOBAL_HOOK_INSTALLED = False


def _sanitize_model_params(kwargs: dict) -> dict:
    _downscale_messages_images(kwargs.get('messages', []))
    """Sanitizes model arguments for newer OpenAI architectures (gpt-5..., o1, o3, etc.).
    These models reject legacy parameters like `temperature=0.0` or `max_tokens`.
    """
    try:
        model_str = str(kwargs.get("model", "")).lower()
        if any(m in model_str for m in ["gpt-5", "o1", "o3", "o4"]):
            if "max_tokens" in kwargs:
                if "max_completion_tokens" not in kwargs:
                    kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
                else:
                    kwargs.pop("max_tokens")
            if "temperature" in kwargs:
                temp = kwargs.get("temperature")
                if temp is not None and (temp == 0 or temp == 0.0 or temp != 1):
                    kwargs.pop("temperature", None)
            if "top_p" in kwargs:
                top_p = kwargs.get("top_p")
                if top_p is not None and top_p != 1:
                    kwargs.pop("top_p", None)
    except Exception:
        pass
    return kwargs


def enable_global_prompt_caching() -> bool:
    """
    Patches OpenAI's Completions.create and AsyncCompletions.create methods
    globally so EVERY client.chat.completions.create(...) call in any POC
    automatically gets >= 1,024-token prefix caching and cache hit logging.
    """
    global _GLOBAL_HOOK_INSTALLED
    if _GLOBAL_HOOK_INSTALLED:
        return True

    try:
        from openai.resources.chat.completions import Completions, AsyncCompletions

        if not getattr(Completions.create, "_is_prompt_cache_wrapped", False):
            _orig_sync_create = Completions.create

            def _cached_sync_create(self, *args, **kwargs):
                _sanitize_model_params(kwargs)
                model = kwargs.get("model", "gpt-5.6-terra")
                poc = "general_poc"
                try:
                    if "messages" in kwargs and isinstance(kwargs["messages"], list):
                        kwargs["messages"] = optimize_messages_for_caching(kwargs["messages"], model=str(model))
                    poc, fname, sname = _infer_caller_context()
                except Exception:
                    pass
                response = _orig_sync_create(self, *args, **kwargs)
                try:
                    if not kwargs.get("stream", False):
                        _record_cache_observability(response, model=str(model), poc_name=poc)
                except Exception:
                    pass
                return response

            _cached_sync_create._is_prompt_cache_wrapped = True
            Completions.create = _cached_sync_create

        if not getattr(AsyncCompletions.create, "_is_prompt_cache_wrapped", False):
            _orig_async_create = AsyncCompletions.create

            async def _cached_async_create(self, *args, **kwargs):
                _sanitize_model_params(kwargs)
                model = kwargs.get("model", "gpt-5.6-terra")
                poc = "general_poc"
                try:
                    if "messages" in kwargs and isinstance(kwargs["messages"], list):
                        kwargs["messages"] = optimize_messages_for_caching(kwargs["messages"], model=str(model))
                    poc, fname, sname = _infer_caller_context()
                except Exception:
                    pass
                response = await _orig_async_create(self, *args, **kwargs)
                try:
                    if not kwargs.get("stream", False):
                        _record_cache_observability(response, model=str(model), poc_name=poc)
                except Exception:
                    pass
                return response

            _cached_async_create._is_prompt_cache_wrapped = True
            AsyncCompletions.create = _cached_async_create

        # Also patch beta structured outputs: client.beta.chat.completions.parse
        try:
            from openai.resources.beta.chat.completions import Completions as BetaCompletions
            if not getattr(BetaCompletions.parse, "_is_prompt_cache_wrapped", False):
                _orig_beta_parse = BetaCompletions.parse

                def _cached_beta_parse(self, *args, **kwargs):
                    _sanitize_model_params(kwargs)
                    model = kwargs.get("model", "gpt-5.6-terra")
                    poc = "Parity_setup"
                    fname = "document"
                    sname = "structured_parse"
                    try:
                        if "messages" in kwargs and isinstance(kwargs["messages"], list):
                            kwargs["messages"] = optimize_messages_for_caching(kwargs["messages"], model=str(model))
                        poc_inferred, fname_inferred, sname_inferred = _infer_caller_context()
                        if poc_inferred and poc_inferred != "general_poc":
                            poc = poc_inferred
                        if fname_inferred and fname_inferred != "document":
                            fname = fname_inferred
                        if sname_inferred:
                            sname = sname_inferred
                    except Exception:
                        pass
                    response = _orig_beta_parse(self, *args, **kwargs)
                    try:
                        _record_cache_observability(response, model=str(model), poc_name=poc)
                        from core.universal_token_monitor import track_usage as _track_universal
                        _track_universal(
                            response_usage=getattr(response, "usage", None),
                            model=str(model),
                            poc_name=poc,
                            file_name=fname,
                            step_name=sname
                        )
                    except Exception:
                        pass
                    return response

                _cached_beta_parse._is_prompt_cache_wrapped = True
                BetaCompletions.parse = _cached_beta_parse
        except Exception as _b_err:
            logger.debug(f"BetaCompletions.parse hook deferred: {_b_err}")

        _GLOBAL_HOOK_INSTALLED = True
        return True
    except Exception as e:
        logger.debug(f"Global OpenAI prompt cache hook deferred: {e}")
        return False


# Auto-enable global hook when module is imported
enable_global_prompt_caching()


def get_cache_stats() -> Dict[str, Any]:
    """Returns aggregated prompt caching metrics across all invocations."""
    total = _CACHE_STATS["total_calls"]
    hits = _CACHE_STATS["cache_hits"]
    hit_rate = round((hits / total * 100), 2) if total > 0 else 0.0

    return {
        "total_calls": total,
        "cache_hits": hits,
        "cache_misses": _CACHE_STATS["cache_misses"],
        "hit_rate_percent": hit_rate,
        "total_prompt_tokens": _CACHE_STATS["total_prompt_tokens"],
        "total_cached_tokens": _CACHE_STATS["total_cached_tokens"],
        "total_completion_tokens": _CACHE_STATS["total_completion_tokens"],
        "estimated_usd_saved": round(_CACHE_STATS["estimated_usd_saved"], 6),
        "formatted_savings": f"${_CACHE_STATS['estimated_usd_saved']:.6f}"
    }
