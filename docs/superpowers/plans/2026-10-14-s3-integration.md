# S3 Storage Integration & Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an async S3 storage service in the backend, enable fast in-memory S3 testing with `moto`, and integrate MinIO into `compose.yaml` for local development.

**Architecture:** Create `app.core.storage` using `aioboto3` (with fallback to `boto3`) initialized from `app.core.settings`. Support both Railway's `S3_*` env vars and standard `AWS_*` env vars via Pydantic `AliasChoices`. Enable instant zero-Docker unit testing in `pytest` with `moto[s3]`. Provision MinIO and an automatic bucket provisioning container in `compose.yaml` for local stack execution.

**Tech Stack:** Python 3.14, FastAPI, aioboto3, boto3, moto[s3], MinIO, Docker Compose.

**Spec:** `docs/specs/sentinela/01-architecture.md`, `.railway/railway.ts`, `ADR-001`.

## Global Constraints
- Python >=3.14 toolchain managed via `uv`.
- Async I/O: no blocking network calls on FastAPI event loop.
- API and environment backward compatibility: all S3 settings remain optional (`s3_bucket_name` default `""`).
- Never commit secrets to git.

## Review Focus
- Unconfigured storage: `StorageService` raises or safely reports when S3 credentials/bucket are not set, without crashing app boot.
- Presigned URLs: Presigned download/upload URLs respect expiration parameters.
- File not found: Download and delete operations handle `ClientError` (NoSuchKey) gracefully.
- Env var precedence: `S3_*` and `AWS_*` variables map properly to settings without conflict.
- Local Compose networking: API inside docker communicates with `http://minio:9000`, while host browser/tools use `http://localhost:9000`.

---

### Task 1: S3 Dependencies & Settings Aliases

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/settings.py`
- Modify: `backend/tests/test_settings.py`

**Interfaces:**
- Consumes: `Settings` in `app.core.settings`
- Produces: `settings.s3_bucket_name`, `settings.s3_endpoint`, `settings.s3_access_key_id`, `settings.s3_secret_access_key`, `settings.s3_region` supporting `AWS_*` aliases.

- [ ] **Step 1: Add S3 dependencies to `backend/pyproject.toml`**
Add `aioboto3` and `boto3` to runtime dependencies, and `moto[s3]` to dev dependencies. Run `uv sync`.

- [ ] **Step 2: Update `backend/app/core/settings.py` with `AliasChoices`**
Allow `s3_endpoint` to read from `s3_endpoint` or `aws_endpoint_url`, `s3_access_key_id` from `s3_access_key_id` or `aws_access_key_id`, `s3_secret_access_key` from `s3_secret_access_key` or `aws_secret_access_key`, and `s3_region` from `s3_region`, `aws_default_region`, or `aws_region`.

- [ ] **Step 3: Update `backend/tests/test_settings.py`**
Ensure tests isolate from any `.env` file on disk by passing `_env_file=None` for default assertions, and add a test verifying `AWS_*` aliases populate `s3_*` settings.

- [ ] **Step 4: Run settings test to verify it passes**
Run: `uv run pytest tests/test_settings.py -v`
Expected: PASS (all tests pass).

- [ ] **Step 5: Commit**
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
  - `is_configured() -> bool`
  - `upload(key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream") -> str`
  - `download(key: str) -> bytes`
  - `delete(key: str) -> bool`
  - `generate_presigned_url(key: str, expires_in: int = 3600, method: str = "get_object") -> str`
  - `check_health() -> bool`
  - Dependency: `get_storage() -> StorageService`

- [ ] **Step 1: Write failing test in `backend/tests/test_storage.py`**
Use `moto` and `@mock_aws` to verify upload, download, delete, presigned URL generation, unconfigured storage behavior, and health check.

- [ ] **Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_storage.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'app.core.storage')

- [ ] **Step 3: Implement `StorageService` in `backend/app/core/storage.py`**
Implement async methods using `aioboto3.Session` (configured with `s3_endpoint`, `s3_access_key_id`, `s3_secret_access_key`, `s3_region`, `s3_bucket_name`).

- [ ] **Step 4: Run test to verify it passes**
Run: `uv run pytest tests/test_storage.py -v`
Expected: PASS (all storage tests pass).

- [ ] **Step 5: Commit**
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
- Consumes: MinIO Docker image `minio/minio` and MinIO Client `minio/mc`
- Produces: Running S3 endpoint at `http://localhost:9000` (API container accesses `http://minio:9000`), MinIO web console at `http://localhost:9001`, and pre-created bucket `sentinela`.

- [ ] **Step 1: Update `compose.yaml`**
Add `minio` and `minio-create-bucket` services.
Inject S3 environment variables into the `api` service:
```yaml
      S3_ENDPOINT: http://minio:9000
      S3_BUCKET_NAME: sentinela
      S3_ACCESS_KEY_ID: minioadmin
      S3_SECRET_ACCESS_KEY: minioadmin
      S3_REGION: ams
```
Add `miniodata` volume.

- [ ] **Step 2: Update `backend/.env.example`**
Document the local MinIO connection settings alongside Railway settings.

- [ ] **Step 3: Verify Compose configuration syntax**
Run: `docker compose config`
Expected: Valid compose config with services `db`, `api`, `dashboard`, `minio`, `minio-create-bucket`.

- [ ] **Step 4: Commit**
```bash
git add compose.yaml backend/.env.example
git commit -m "feat(infra): add MinIO S3 storage service to local Docker Compose"
```

---

### Task 4: Full Verification

- [ ] **Step 1: Run all backend tests**
Run: `uv run pytest tests/test_settings.py tests/test_storage.py -v`
Expected: All tests pass cleanly.

- [ ] **Step 2: Check git status and diff**
Verify no extraneous files or secrets were committed.
