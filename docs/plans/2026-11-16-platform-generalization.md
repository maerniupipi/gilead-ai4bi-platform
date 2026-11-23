# Platform Generalization Implementation Plan

**Goal:** Deliver the latest complete platform source as an independent, customer-neutral repository.

**Architecture:** Retain platform engines and management features. Replace customer-specific service identity with opaque caller identifiers; expose conversation/export services through generic platform APIs. Keep workflow-based SQL transforms and durable synchronization scheduling without embedded business rules.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL/MySQL, Vue 3, Vite, Redis, pytest, Node test runner.

## 1. Copy and isolate
Copy tracked platform frontend/backend, generic documentation and Excel batch runner to this directory. Exclude runtime environments, customer client applications, integration packages, credentials and old Git history. Preserve unrelated local files.

## 2. Generalize API, identity and diagnostics
Move service APIs to `/api/service`, remove imported-history snapshot endpoints and identity migrations. Use an opaque `user` identifier scoped to the authenticated service Key. Replace customer-specific identity fields and UI filters with user identifiers. Preserve streaming, cancellation, export jobs, Key bindings, conversation inspection and trace capture. Update contract/integration tests.

## 3. Remove organization policies from engines
Remove customer identity lookup, whitelist API/model/page, dedicated SQL permission implementation, default-identity installers, role-based recall filtering and business prompt additions. Preserve normal recall, typed input forwarding, history, external HTTP nodes, and configurable SQL-transform workflow invocation. Test native and nested workflows.

## 4. Retain synchronization as a configurable service
Replace fixed upstream interfaces and three built-in tasks with a deployment-configured task registry and HTTP JSON source settings. Keep task leases, cron, progress, staging/COPY and atomic replacement. Remove business-year filtering and external legacy lock-table assumptions. Test pagination, configuration, rollback gates and scheduling in isolation.

## 5. Neutral exports and deployable package
Replace branded PPT assets with neutral editable templates. Remove disabled identity-watermark helpers while preserving safe XLSX generation. Add clean environment examples, platform-only Compose, initialization instructions and a generic batch-runner URL.

## 6. Verify and publish
Run the backend regression suite, meaningful generic-service and synchronization tests, frontend Node tests and both Vite builds, batch-runner tests, application startup/OpenAPI checks, and scan the exported source/assets for removed customer markers and credentials. Initialize a clean Git repository, commit and push main to the requested GitLab project; verify the remote revision.
