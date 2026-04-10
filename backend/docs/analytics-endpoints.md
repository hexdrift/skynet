# Analytics Aggregation Endpoints

## Overview

Three pre-computed aggregation endpoints for dashboard analytics. These endpoints aggregate job metrics on the backend to improve performance when dealing with large datasets (>1000 jobs).

## Endpoints

### GET /analytics/summary

Pre-compute dashboard KPIs across all filtered jobs.

**Query Parameters:**
- `optimizer` (optional): Filter by optimizer name (e.g., `miprov2`, `gepa`)
- `model` (optional): Filter by model name (exact match)
- `status` (optional): Filter by job status (`success`, `failed`, `pending`, etc.)
- `username` (optional): Filter by username

**Response:**
```json
{
  "total_jobs": 150,
  "success_count": 120,
  "failed_count": 25,
  "cancelled_count": 5,
  "pending_count": 0,
  "running_count": 0,
  "success_rate": 0.8,
  "avg_improvement": 0.125,
  "max_improvement": 0.45,
  "min_improvement": -0.02,
  "avg_runtime": 245.5,
  "total_dataset_rows": 15000,
  "total_pairs": 320,
  "completed_pairs": 280,
  "failed_pairs": 40
}
```

**Example:**
```bash
curl "http://localhost:8000/analytics/summary?optimizer=miprov2&status=success"
```

---

### GET /analytics/optimizers

Per-optimizer aggregated statistics.

**Query Parameters:**
- `model` (optional): Filter by model name
- `status` (optional): Filter by job status
- `username` (optional): Filter by username

**Response:**
```json
{
  "items": [
    {
      "name": "miprov2",
      "total_jobs": 85,
      "success_count": 75,
      "avg_improvement": 0.15,
      "success_rate": 0.88,
      "avg_runtime": 180.5
    },
    {
      "name": "gepa",
      "total_jobs": 65,
      "success_count": 45,
      "avg_improvement": 0.22,
      "success_rate": 0.69,
      "avg_runtime": 320.2
    }
  ]
}
```

**Example:**
```bash
curl "http://localhost:8000/analytics/optimizers?model=gpt-4"
```

---

### GET /analytics/models

Per-model aggregated statistics.

**Query Parameters:**
- `optimizer` (optional): Filter by optimizer name
- `status` (optional): Filter by job status
- `username` (optional): Filter by username

**Response:**
```json
{
  "items": [
    {
      "name": "gpt-4",
      "total_jobs": 120,
      "success_count": 105,
      "avg_improvement": 0.18,
      "success_rate": 0.875,
      "use_count": 120
    },
    {
      "name": "gpt-3.5-turbo",
      "total_jobs": 80,
      "success_count": 65,
      "avg_improvement": 0.12,
      "success_rate": 0.8125,
      "use_count": 80
    }
  ]
}
```

**Example:**
```bash
curl "http://localhost:8000/analytics/models?optimizer=miprov2&status=success"
```

---

## Implementation Details

### Job Type Handling

Both regular `run` jobs and `grid_search` jobs are supported:

- **Run jobs**: Metrics extracted directly from `result.baseline_test_metric` and `result.optimized_test_metric`
- **Grid search jobs**: Metrics extracted from `result.best_pair` (the best-performing model pair)

### Aggregation Logic

1. **Fetch all jobs** using `job_store.list_jobs()` with native filters (status, username)
2. **Apply additional filters** (optimizer, model) by parsing `payload_overview`
3. **Aggregate metrics** by iterating through jobs and accumulating:
   - Status counts
   - Metric improvements (optimized - baseline)
   - Runtime statistics
   - Dataset row counts
   - Pair counters (for grid search)
4. **Compute statistics** (averages, rates, min/max)
5. **Return response** with proper Pydantic model validation

### Performance

- Endpoints query up to 10,000 jobs (configurable limit)
- No pagination needed for analytics aggregation
- Efficient in-memory aggregation
- Works with both local and remote (PostgreSQL) storage backends

### Error Handling

- Invalid filter values are silently ignored (no 422 errors)
- Missing or null metrics are handled gracefully
- Empty result sets return valid responses with zero counts
- Follows existing FastAPI error handling patterns

## Testing

Run integration tests:

```bash
cd backend
pytest tests/test_llm_integration.py -v -k analytics
```

Or test manually:

```bash
# Start backend
cd backend && uv run python main.py

# In another terminal
curl http://localhost:8000/analytics/summary | jq
curl http://localhost:8000/analytics/optimizers | jq
curl http://localhost:8000/analytics/models | jq
```

## Frontend Integration

These endpoints are designed to replace client-side aggregation in the frontend analytics tab:

**Before:**
```typescript
// Frontend fetches all jobs and aggregates locally
const jobs = await api.listJobs();
const successRate = jobs.filter(j => j.status === 'success').length / jobs.length;
```

**After:**
```typescript
// Frontend calls pre-computed endpoint
const summary = await api.getAnalyticsSummary({ optimizer: 'miprov2' });
const successRate = summary.success_rate;
```

This dramatically improves performance when dealing with >1000 jobs.
