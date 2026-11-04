import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, 'Sales team - Copy')
from core.universal_token_monitor import track_usage

calls_data = [
    (5747, 0, 312, "invoice_rate_extraction_chunk_1"),
    (5330, 3328, 298, "invoice_rate_extraction_chunk_2"),
    (5787, 2944, 345, "invoice_rate_extraction_chunk_3"),
    (5266, 2944, 280, "invoice_rate_extraction_chunk_4"),
    (5636, 2944, 310, "invoice_rate_extraction_chunk_5"),
    (5304, 2944, 295, "invoice_rate_extraction_chunk_6"),
    (5535, 2944, 305, "invoice_rate_extraction_chunk_7"),
    (5517, 2944, 320, "invoice_rate_extraction_chunk_8"),
    (5515, 2944, 312, "invoice_rate_extraction_chunk_9"),
    (5308, 2944, 290, "invoice_rate_extraction_chunk_10"),
    (4870, 2944, 260, "invoice_rate_extraction_chunk_11"),
    (5051, 2944, 275, "invoice_rate_extraction_chunk_12"),
    (4932, 2944, 285, "invoice_rate_extraction_chunk_13"),
    (4583, 2944, 250, "invoice_rate_extraction_chunk_14"),
    (4180, 2944, 235, "invoice_rate_extraction_chunk_15"),
]

file_name = "c3cfecb1-3c50-42ad-9423-ed8c33dc5175_RENEWAL.pdf"
session_id = "2026-11-03 13:36:00 UTC [709-15]"

for prompt_tokens, cached_tokens, completion_tokens, step in calls_data:
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens)
    )
    track_usage(
        response_usage=usage,
        model="gpt-4o",
        poc_name="RENEWAL_PROCESS",
        file_name=file_name,
        step_name=step,
        session_id=session_id
    )

print("Backfilled 15 Renewal Process calls into universal_token_usage.db successfully!")

