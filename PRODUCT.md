# Product

<!-- impeccable:product-schema 1 -->

This file is the compact product contract used by repository tooling. For the narrative product description and current delivery status, see [`docs/PRODUCT_DESCRIPTION.md`](docs/PRODUCT_DESCRIPTION.md) and [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md).

## Platform

Web application.

## Stack

React, Vite, TypeScript, CSS, FastAPI, PostgreSQL/Supabase, private Google Cloud Storage and GCP Batch.

## Users

Perception ML engineers, labeling QA auditors, reviewers and administrators who inspect autonomous-driving datasets and resolve annotation-quality issues.

## Product purpose

Label Guardian provides an auditable QA workflow for perception datasets. It helps teams ingest dataset metadata, prioritize risky frames, review detected issues, correct camera-image annotations in the 2D Editor and preserve every decision as a revision and audit event.

## Current scope

- Authenticated QA queue, case review, reports, settings and role-aware administration.
- Camera-image review and 2D annotation editing.
- API-backed production data; local mock mode is available only for development and demos.
- Immutable annotation revisions with optimistic concurrency checks.
- Private GCS asset access mediated by the backend.
- Deterministic QA checks, with LLM output treated as advisory evidence rather than the source of truth.
- Official-dataset ingestion through dedicated workers and GCP Batch for long-running jobs.

Point-cloud streaming and full 3D annotation editing are future capabilities, not current product claims.

## Brand commitments

- Dark, high-contrast interface designed for prolonged inspection work.
- Teal primary actions, restrained semantic colors and shared design tokens.
- Clear loading, empty, error and authorization states.
- Keyboard-accessible controls and visible focus states for core workflows.

## Product principles

1. **Auditability:** preserve provenance, reviewer decisions and annotation history.
2. **Fail closed:** production does not silently substitute mock data when an API or authorization check fails.
3. **Actionable evidence:** surface reproducible issue evidence instead of opaque model conclusions.
4. **Focused review:** optimize information density and interaction flow for repetitive QA work.
5. **Contract ownership:** derive API and schema claims from OpenAPI, migrations and source code.
