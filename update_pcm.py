with open('Sales team - Copy/core/prompt_cache_manager.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''        # Also patch beta structured outputs: client.beta.chat.completions.parse
        try:
            from openai.resources.beta.chat.completions import Completions as BetaCompletions
            if not getattr(BetaCompletions.parse, "_is_prompt_cache_wrapped", False):
                _orig_beta_parse = BetaCompletions.parse

                def _cached_beta_parse(self, *args, **kwargs):
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
            logger.debug(f"BetaCompletions.parse hook deferred: {_b_err}")'''

replacement = '''        # Also patch structured outputs: client.beta.chat.completions.parse and client.chat.completions.parse
        try:
            target_classes = [Completions, AsyncCompletions]
            try:
                from openai.resources.beta.chat.completions import Completions as BetaCompletions
                target_classes.append(BetaCompletions)
            except Exception:
                pass

            for cls in target_classes:
                if hasattr(cls, "parse") and not getattr(cls.parse, "_is_prompt_cache_wrapped", False):
                    _orig_p = cls.parse
                    is_async = (cls is AsyncCompletions) or "async" in cls.__name__.lower()

                    if is_async:
                        async def _cached_parse_async(self, *args, _orig=_orig_p, **kwargs):
                            model = kwargs.get("model", "gpt-5.6-terra")
                            poc = "Parity_setup"
                            fname = "document"
                            sname = "universal_extraction"
                            try:
                                if "messages" in kwargs and isinstance(kwargs["messages"], list):
                                    kwargs["messages"] = optimize_messages_for_caching(kwargs["messages"], model=str(model))
                                poc_inferred, fname_inferred, sname_inferred = _infer_caller_context()
                                if poc_inferred and poc_inferred != "general_poc":
                                    poc = poc_inferred
                                if fname_inferred and fname_inferred != "document":
                                    fname = fname_inferred
                                if sname_inferred and sname_inferred != "llm_call":
                                    sname = sname_inferred
                            except Exception:
                                pass
                            response = await _orig(self, *args, **kwargs)
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

                        _cached_parse_async._is_prompt_cache_wrapped = True
                        cls.parse = _cached_parse_async
                    else:
                        def _cached_parse_sync(self, *args, _orig=_orig_p, **kwargs):
                            model = kwargs.get("model", "gpt-5.6-terra")
                            poc = "Parity_setup"
                            fname = "document"
                            sname = "universal_extraction"
                            try:
                                if "messages" in kwargs and isinstance(kwargs["messages"], list):
                                    kwargs["messages"] = optimize_messages_for_caching(kwargs["messages"], model=str(model))
                                poc_inferred, fname_inferred, sname_inferred = _infer_caller_context()
                                if poc_inferred and poc_inferred != "general_poc":
                                    poc = poc_inferred
                                if fname_inferred and fname_inferred != "document":
                                    fname = fname_inferred
                                if sname_inferred and sname_inferred != "llm_call":
                                    sname = sname_inferred
                            except Exception:
                                pass
                            response = _orig(self, *args, **kwargs)
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

                        _cached_parse_sync._is_prompt_cache_wrapped = True
                        cls.parse = _cached_parse_sync
        except Exception as _b_err:
            logger.debug(f"Completions.parse hook deferred: {_b_err}")'''

content_norm = content.replace('\r\n', '\n')
target_norm = target.replace('\r\n', '\n')
if target_norm in content_norm:
    new_content = content_norm.replace(target_norm, replacement)
    with open('Sales team - Copy/core/prompt_cache_manager.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('SUCCESS')
else:
    print('TARGET NOT FOUND')

