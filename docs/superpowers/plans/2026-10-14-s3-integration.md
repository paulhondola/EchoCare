# S3 Storage Integration & Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an async S3 storage service in the backend, enable fast in-memory S3 testing with `moto`, and integrate MinIO into `compose.yaml` for local development.

**Architecture:** Create `app.core.storage` using synchronous `boto3` clients (built once, reused) whose calls run on the service's own small thread pool, initialized from `app.core.settings`. Settings read Railway's `S3_*` env vars only; with them empty, boto3's own chain still reads `AWS_*`. Enable instant zero-Docker unit testing in `pytest` with `moto[s3]`. Provision MinIO and an automatic bucket provisioning container in `compose.yaml` for local stack execution.

**Tech Stack:** Python 3.14, FastAPI, boto3, moto[s3], MinIO (`cgr.dev/chainguard/minio`), Docker Compose.

**Spec:** `docs/specs/sentinela/01-architecture.md`, `.railway/railway.ts`, `ADR-001`.

## Global Constraints
- Python >=3.14 toolchain managed via `uv`.
- Async I/O: no blocking network calls on FastAPI event loop.
- API and environment backward compatibility: all S3 settings remain optional (`s3_bucket_name` default `""`).
- Never commit secrets to git.

## Review Focus
- Unconfigured storage: `StorageService` raises or safely reports when S3 credentials/bucket are not set, without crashing app boot.
- Presigned URLs: download URLs and upload forms respect expiration (1 s to 7 days, SigV4's limit); upload forms enforce Content-Type and size.
- File not found: download raises `FileNotFoundError` on NoSuchKey; every other boto3 failure is a `StorageError`. Delete of a missing key succeeds (S3 is idempotent).
- Env vars: `S3_*` variables (the names `railway.ts` sets) map to settings; `AWS_*` are left to boto3.
- Local Compose networking: API inside docker communicates with `http://minio:9000`, while presigned URLs are signed for `S3_PUBLIC_ENDPOINT` (`http://localhost:9000`), which host browsers and tools can open.

---

### Task 1: S3 Dependencies & Settings

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/settings.py`
- Modify: `backend/tests/test_settings.py`

**Interfaces:**
- Consumes: `Settings` in `app.core.settings`
- Produces: `settings.s3_bucket_name`, `settings.s3_endpoint`, `settings.s3_access_key_id`, `settings.s3_secret_access_key`, `settings.s3_region`, `settings.s3_public_endpoint`.

- [x] **Step 1: Add S3 dependencies to `backend/pyproject.toml`**
Add `boto3` to runtime dependencies, and `moto[s3]` to dev dependencies. Run `uv sync`.

- [x] **Step 2: Update `backend/app/core/settings.py`**
Add `s3_public_endpoint` (the host in presigned URLs; empty means `s3_endpoint`). No `AWS_*` aliases: `railway.ts` sets `S3_*`, and boto3 reads `AWS_*` itself.

- [x] **Step 3: Update `backend/tests/test_settings.py`**
Ensure tests isolate from any `.env` file on disk by passing `_env_file=None` and clearing `S3_*` from the environment for default assertions, and add a test verifying `S3_*` env vars populate the settings.

- [x] **Step 4: Run settings test to verify it passes**
Run: `uv run pytest tests/test_settings.py -v`
Expected: PASS (all tests pass).

- [x] **Step 5: Commit**
```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/settings.py backend/tests/test_settings.py
git commit -m "feat(backend): add S3 dependencies and alias support in settings"
```

---

### Task 2: Storage Service (`app.core.storage`)

**Files:**
- Create: `backend/app/core/storage.py`
- Create: `backend/tests/test_storage.py`

**Interfaces:**
- Consumes: `Settings` from `app.core.settings`
- Produces: `StorageService` with methods:
  - `is_configured -> bool` (a property)
  - `upload(key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream") -> None`
  - `download(key: str) -> bytes`
  - `delete(key: str) -> None`
  - `generate_presigned_url(key: str, expires_in: int = 3600) -> str` (download only)
  - `generate_presigned_post(key: str, content_type: str, max_bytes: int, expires_in: int = 3600) -> dict` (upload form)
  - `check_health() -> bool`
  - Dependency: `get_storage() -> StorageService`

- [x] **Step 1: Write failing test in `backend/tests/test_storage.py`**
Use `moto` and `@mock_aws` to verify upload, download, delete, presigned URL generation, unconfigured storage behavior, and health check.

- [x] **Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_storage.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'app.core.storage')

- [x] **Step 3: Implement `StorageService` in `backend/app/core/storage.py`**
Implement async methods over one reused `boto3` client per endpoint, run on the service's own thread pool with bounded timeouts and retries (configured with `s3_endpoint`, `s3_access_key_id`, `s3_secret_access_key`, `s3_region`, `s3_bucket_name`, and `s3_public_endpoint` for presigning).

- [x] **Step 4: Run test to verify it passes**
Run: `uv run pytest tests/test_storage.py -v`
Expected: PASS (all storage tests pass).

- [x] **Step 5: Commit**
```bash
git add backend/app/core/storage.py backend/tests/test_storage.py
git commit -m "feat(backend): add async S3 storage service with moto test coverage"
```

---

### Task 3: Local Dev & Compose MinIO Integration

**Files:**
- Modify: `compose.yaml`
- Modify: `backend/.env.example`

**Interfaces:**
- Consumes: Docker image `cgr.dev/chainguard/minio`, which also ships the MinIO Client `mc`
- Produces: Running S3 endpoint at `http://localhost:9000` (API container accesses `http://minio:9000`), MinIO web console at `http://localhost:9001`, and pre-created bucket `sentinela`.

- [x] **Step 1: Update `compose.yaml`**
Add `minio` and `minio-create-bucket` services.
Inject S3 environment variables into the `api` service, each overridable from the root `.env` (MinIO's root keys and the created bucket read the same variables):
```yaml
      S3_ENDPOINT: ${S3_ENDPOINT:-http://minio:9000}
      S3_PUBLIC_ENDPOINT: ${S3_PUBLIC_ENDPOINT:-http://localhost:9000}
      S3_BUCKET_NAME: ${S3_BUCKET_NAME:-sentinela}
      S3_ACCESS_KEY_ID: ${S3_ACCESS_KEY_ID:-minioadmin}
      S3_SECRET_ACCESS_KEY: ${S3_SECRET_ACCESS_KEY:-minioadmin}
      S3_REGION: ${S3_REGION:-ams}
```
The `api` waits for `minio-create-bucket` to complete, with `required: false` so a broken MinIO doesn't stop the API.
Add `miniodata` volume.

- [x] **Step 2: Update `backend/.env.example`**
Document the local MinIO connection settings alongside Railway settings.

- [x] **Step 3: Verify Compose configuration syntax**
Run: `docker compose config`
Expected: Valid compose config with services `db`, `api`, `dashboard`, `minio`, `minio-create-bucket`.

- [x] **Step 4: Commit**
```bash
git add compose.yaml backend/.env.example
git commit -m "feat(infra): add MinIO S3 storage service to local Docker Compose"
```

---

### Task 4: Full Verification

- [x] **Step 1: Run all backend tests**
Run: `uv run pytest tests/test_settings.py tests/test_storage.py -v`
Expected: All tests pass cleanly.

- [x] **Step 2: Check git status and diff**
Verify no extraneous files or secrets were committed.
