try:
    import os
    import sys
    from pathlib import Path

    _ws = Path(__file__).resolve().parent.parent / "Sales team - Copy"
    if str(_ws) not in sys.path:
        sys.path.insert(0, str(_ws))

    from core.prompt_cache_manager import (
        enable_global_prompt_caching,
        optimize_messages_for_caching,
        _record_cache_observability
    )
    enable_global_prompt_caching()

    def _infer_exact_subprocess_context():
        """Accurately identifies the real POC engine and file name from the execution call stack."""
        poc_name = "general_poc"
        file_name = "document"
        step_name = "llm_call"

        try:
            frame = sys._getframe(2)
            while frame:
                co_file = frame.f_code.co_filename
                if co_file and "sitecustomize" not in co_file and "prompt_cache_manager" not in co_file and "openai" not in co_file.lower():
                    p_str = str(Path(co_file).resolve())
                    # Stack frame path is the ground truth
                    if "Renewal_process" in p_str:
                        poc_name = "RENEWAL_PROCESS"
                    elif "\\rpve\\" in p_str.lower() or "/rpve/" in p_str.lower():
                        poc_name = "RPVE"
                    elif "Parity_setup" in p_str:
                        poc_name = "PARITY_SETUP"
                    elif "base-claim" in p_str.lower():
                        poc_name = "BASE-CLAIM"
                    elif "Invoice-to-excel" in p_str:
                        poc_name = "INVOICE_EXCEL"
                    elif "Payroll_extractor" in p_str:
                        poc_name = "PAYROLL"
                    elif "summary & chatbot" in p_str:
                        poc_name = "SOP SUMMARIZER"
                    elif "Notice-extraction" in p_str:
                        poc_name = "NOTICE_EXTRACTION"
                    elif "Gpu_server" in p_str:
                        poc_name = "GPU_SERVER"

                    step_name = frame.f_code.co_name or step_name

                    # Look for filename in local variables
                    f_locals = frame.f_locals
                    for key in ("file_name", "filename", "safe_filename", "pdf_path", "file_path", "working_path", "census_name"):
                        val = f_locals.get(key)
                        if val and isinstance(val, (str, Path)):
                            candidate = os.path.basename(str(val)).strip()
                            if candidate and not any(candidate.lower().endswith(ext) for ext in ('.py', '.pyc')):
                                file_name = candidate
                                break
                    if poc_name != "general_poc" and file_name != "document":
                        break
                frame = frame.f_back
        except Exception:
            pass

        # If file_name is still placeholder, check context/env
        if file_name == "document":
            try:
                from core.universal_token_monitor import get_context
                ctx = get_context()
                if ctx.get("file_name"):
                    file_name = ctx["file_name"]
                elif os.environ.get("COGNET_ACTIVE_FILE_NAME"):
                    file_name = os.environ["COGNET_ACTIVE_FILE_NAME"]
            except Exception:
                pass

        return poc_name, file_name, step_name

    from openai.resources.chat.completions import Completions, AsyncCompletions

    if not getattr(Completions.create, "_is_full_token_monitor_wrapped", False):
        _orig_create = Completions.create

        def _monitored_create(self, *args, **kwargs):
            model = kwargs.get("model", "gpt-5.6-terra")
            try:
                if "messages" in kwargs and isinstance(kwargs["messages"], list):
                    kwargs["messages"] = optimize_messages_for_caching(kwargs["messages"], model=str(model))
                poc, fname, sname = _infer_exact_subprocess_context()
            except Exception:
                poc, fname, sname = "general_poc", "document", "llm_call"

            response = _orig_create(self, *args, **kwargs)

            try:
                _record_cache_observability(response, model=str(model), poc_name=poc)
            except Exception:
                pass

            try:
                from core.universal_token_monitor import track_usage
                track_usage(
                    response_usage=getattr(response, "usage", None),
                    model=str(model),
                    poc_name=poc,
                    file_name=fname,
                    step_name=sname
                )
            except Exception:
                pass

            return response

        _monitored_create._is_full_token_monitor_wrapped = True
        Completions.create = _monitored_create

    # Also wrap Completions.parse if available
    for _cls in (Completions, AsyncCompletions):
        if hasattr(_cls, "parse") and not getattr(_cls.parse, "_is_full_token_monitor_wrapped", False):
            _orig_parse = _cls.parse
            _is_async = (_cls is AsyncCompletions) or "async" in _cls.__name__.lower()

            if not _is_async:
                def _monitored_parse(self, *args, _orig=_orig_parse, **kwargs):
                    model = kwargs.get("model", "gpt-5.6-terra")
                    try:
                        if "messages" in kwargs and isinstance(kwargs["messages"], list):
                            kwargs["messages"] = optimize_messages_for_caching(kwargs["messages"], model=str(model))
                        poc, fname, sname = _infer_exact_subprocess_context()
                    except Exception:
                        poc, fname, sname = "general_poc", "document", "parse"

                    response = _orig(self, *args, **kwargs)
                    try:
                        _record_cache_observability(response, model=str(model), poc_name=poc)
                        from core.universal_token_monitor import track_usage
                        track_usage(
                            response_usage=getattr(response, "usage", None),
                            model=str(model),
                            poc_name=poc,
                            file_name=fname,
                            step_name=sname
                        )
                    except Exception:
                        pass
                    return response

                _monitored_parse._is_full_token_monitor_wrapped = True
                _cls.parse = _monitored_parse

except Exception:
    pass
