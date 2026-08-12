# Token Monitor Integration Guide

## When adding a new POC — just add 2 lines after every OpenAI call

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.universal_token_monitor import track_usage

# Your existing OpenAI call — DO NOT change this
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[...]
)

# ADD THESE 2 LINES right after:
track_usage(response.usage, model="gpt-4o",
            poc_name="your-poc-name", file_name=filename, step_name="extraction")
```

## Parameters

| Parameter | Required | Example | Description |
|---|---|---|---|
| `response_usage` | Yes | `response.usage` | The usage object from OpenAI response |
| `model` | Yes | `"gpt-4o"` | Model name used |
| `poc_name` | Yes | `"file-classification"` | Name of your POC |
| `file_name` | Yes | `"invoice_101.pdf"` | File being processed |
| `step_name` | No | `"ocr_extraction"` | Name of the processing step |
| `session_id` | No | `request_id` | Group multiple files together |

## Where data is stored

- **SQLite DB**: `monitor/universal_token_usage.db`
- **JSON Summary**: `monitor/universal_token_summary.json`
- **Log file**: `monitor/token_monitor.log`

## Querying data

```python
from core.universal_token_monitor import get_summary, get_recent_calls

# Get grand totals + per-POC breakdown
summary = get_summary()

# Get summary for one POC only
poc_data = get_summary(poc_name="file-classification")

# Get all calls for one specific file
file_data = get_summary(file_name="invoice_101.pdf")

# Get recent 50 calls for dashboard
recent = get_recent_calls(limit=50)
```
