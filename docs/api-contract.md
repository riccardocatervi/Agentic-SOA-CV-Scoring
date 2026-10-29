# API contract

**Status: draft.** This is what the backend exposes today. The existing frontend is an external
constraint we cannot change, so every endpoint, field and error format below must be checked
against the frontend code before this document is approved by all three of us.

Open points to check in the frontend:
- paths and HTTP methods
- names of the form fields and of the JSON fields
- how errors are shown (status codes, message format)
- how it displays waiting (polling interval, what it does with `step`)
- how it renders the result and the suggestions

## Endpoints

### `GET /api/health`

`200 {"status": "ok"}`

### `POST /api/analyze`

Starts an analysis. `multipart/form-data` with two fields:

| Field | Type | Notes |
|---|---|---|
| `cv` | file | `.pdf` or `.docx`, up to 5 MB, content checked (not only the extension) |
| `jd_text` | text | the job description, up to 20,000 characters |

Responses:

| Status | Meaning |
|---|---|
| `202` | accepted, body `{"job_id": "<id>"}` |
| `400` | the CV is rejected (wrong type, empty, too big, corrupted header) |
| `413` | the job description is too long |
| `422` | a field is missing or the job description is empty |
| `503` | the queue is full, try again later |

### `GET /api/jobs/{job_id}`

Poll this until `status` is `done` or `failed`.

```json
{
  "id": "…",
  "status": "queued | processing | done | failed",
  "step": "Verifying the quotes against the CV",
  "result": null,
  "error": null
}
```

- `step` is a short, human-readable text, set while `status` is `processing`.
- `result` is set when `status` is `done`:

```json
{
  "score": 72,
  "breakdown": {
    "score": 72,
    "must_met": 4,
    "must_total": 6,
    "nice_met": 1,
    "nice_total": 2,
    "per_requirement": [
      {
        "requirement_id": 1,
        "kind": "must",
        "verdict": "yes | partial | no",
        "verified": true,
        "weight": 3,
        "outcome": 1.0,
        "points": 3.0
      }
    ]
  },
  "suggestions": [{"requirement_id": 3, "text": "If you used Docker in a project, say so."}]
}
```

- `error` is set when `status` is `failed`. It is always a message safe to show to the user.
- `404` means the job is unknown or expired (finished jobs are forgotten after `JOB_TTL_SECONDS`).

## Rules

- The score is a heuristic computed by code from the model's per-requirement verdicts. The UI
  should present it as an estimate, not as a truth.
- Verdicts are `yes`, `partial`, `no` (English).
- Uploaded CVs are deleted when the job ends. Logs never contain CV or job description text.
