import sys

file_path = 'Sales team - Copy/Parity_setup/backend/api_server.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add hook at top after imports
hook_code = '''
# ---------------------------------------------------------------------------
# Global Prompt Caching & Universal Token Monitor Hook for Parity Setup
# ---------------------------------------------------------------------------
try:
    _ws_root = Path(__file__).resolve().parents[2]
    if str(_ws_root) not in sys.path:
        sys.path.insert(0, str(_ws_root))
    
    from core.prompt_cache_manager import enable_global_prompt_caching, optimize_messages_for_caching, _record_cache_observability
    enable_global_prompt_caching()

    from openai.resources.chat.completions import Completions, AsyncCompletions
    for _cls in (Completions, AsyncCompletions):
        if hasattr(_cls, "parse") and not getattr(_cls.parse, "_is_parity_cache_wrapped", False):
            _orig_parse = _cls.parse
            _is_async = (_cls is AsyncCompletions) or "async" in _cls.__name__.lower()

            if _is_async:
                async def _wrapped_parse_async(self, *args, _orig=_orig_parse, **kwargs):
                    model = kwargs.get("model", "gpt-5.6-terra")
                    if "messages" in kwargs and isinstance(kwargs["messages"], list):
                        try:
                            kwargs["messages"] = optimize_messages_for_caching(kwargs["messages"], model=str(model))
                        except Exception:
                            pass
                    response = await _orig(self, *args, **kwargs)
                    try:
                        _record_cache_observability(response, model=str(model), poc_name="PARITY_SETUP")
                        from core.universal_token_monitor import track_usage, get_context
                        ctx = get_context()
                        fname = ctx.get("file_name") or "parity_document.pdf"
                        track_usage(
                            response_usage=getattr(response, "usage", None),
                            model=str(model),
                            poc_name="PARITY_SETUP",
                            file_name=fname,
                            step_name="universal_extraction"
                        )
                    except Exception:
                        pass
                    return response

                _wrapped_parse_async._is_parity_cache_wrapped = True
                _cls.parse = _wrapped_parse_async
            else:
                def _wrapped_parse_sync(self, *args, _orig=_orig_parse, **kwargs):
                    model = kwargs.get("model", "gpt-5.6-terra")
                    if "messages" in kwargs and isinstance(kwargs["messages"], list):
                        try:
                            kwargs["messages"] = optimize_messages_for_caching(kwargs["messages"], model=str(model))
                        except Exception:
                            pass
                    response = _orig(self, *args, **kwargs)
                    try:
                        _record_cache_observability(response, model=str(model), poc_name="PARITY_SETUP")
                        from core.universal_token_monitor import track_usage, get_context
                        ctx = get_context()
                        fname = ctx.get("file_name") or "parity_document.pdf"
                        track_usage(
                            response_usage=getattr(response, "usage", None),
                            model=str(model),
                            poc_name="PARITY_SETUP",
                            file_name=fname,
                            step_name="universal_extraction"
                        )
                    except Exception:
                        pass
                    return response

                _wrapped_parse_sync._is_parity_cache_wrapped = True
                _cls.parse = _wrapped_parse_sync
except Exception as _hook_err:
    print(f"[PARITY PROMPT CACHE] Hook warning: {_hook_err}")
# ---------------------------------------------------------------------------
'''

# 2. Add set_context in process_extraction_task
ctx_target = 'print(f"\\n📂 Processing File: {filename}")'
ctx_replacement = '''print(f"\\n📂 Processing File: {filename}")
        try:
            from core.universal_token_monitor import set_context
            set_context(poc_name="PARITY_SETUP", file_name=filename)
        except Exception:
            pass'''

if hook_code.strip() not in content:
    # insert before load_dotenv()
    idx = content.find('load_dotenv()')
    if idx != -1:
        content = content[:idx] + hook_code + '\n' + content[idx:]
        print("Hook code inserted successfully.")

if ctx_target in content and 'set_context(poc_name="PARITY_SETUP"' not in content:
    content = content.replace(ctx_target, ctx_replacement, 1)
    print("Context tracking inserted into process_extraction_task.")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Saved api_server.py successfully.")

