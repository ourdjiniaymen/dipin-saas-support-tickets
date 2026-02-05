# Backend – Support Ticket Ingestion & Analytics

## Overview

This project implements a minimal, production-oriented backend for ingesting and analyzing support tickets in a multi-tenant SaaS context.

The implementation focuses on correctness, scalability, and clarity of core data flows rather than feature completeness.

---

## Architecture (High Level)

- **API**: FastAPI endpoints for ingestion, analytics, and health checks
- **Ingestion**: Manual pagination from an external SaaS API
- **Storage**: MongoDB with compound indexes
- **Analytics**: MongoDB aggregation pipelines (DB-side computation)
- **Concurrency control**: Per-tenant distributed locking using MongoDB atomics

---

## Ingestion Flow (Core Priority)

For a given tenant, ingestion follows this strict sequence:

1. **Acquire a per-tenant lock**
   - Implemented using a single atomic `findOneAndUpdate`
   - Prevents concurrent ingestion for the same tenant
   - Lock expiration prevents zombie locks

2. **Fetch tickets with manual pagination**
   - Explicit `while` loop
   - Pagination stops when the external API returns no data
   - No helper or retry libraries used

3. **Classify tickets**
   - Simple rule-based classification
   - Adds: `urgency`, `sentiment`, `requires_action`
   - Kept intentionally simple to remain deterministic and explainable

4. **Idempotent persistence**
   - Tickets are upserted using `(tenant_id, ticket_id)`
   - Prevents duplicates when ingestion is re-run

5. **Release the lock**
   - Guaranteed via `try/finally`

---

## Data Model & Idempotency

- **Tickets collection**
  - Unique compound index on `(tenant_id, ticket_id)`
  - Compound index on `(tenant_id, created_at)` for analytics

- **Locks collection**
  - One lock per tenant
  - Managed exclusively via MongoDB atomic operations
  - No external lock systems (Redis, etc.)

Idempotency is guaranteed by design: re-running ingestion updates existing tickets instead of duplicating them.

---

## Analytics Strategy

All statistics are computed **inside MongoDB** using aggregation pipelines:

- `$match` for tenant isolation
- `$group` for counts and distributions
- `$sort` / `$project` for final shaping

No Python-side iteration over raw documents is used.
This ensures predictable performance for 10k+ tickets.

---


## Key Technical Decisions

**UUID-based job tracking:**
- Job IDs generated as UUIDs before any database write
- Used consistently as: lock owner_id, ingestion_jobs._id, ingestion_logs.job_id
- Avoids ObjectId conversion complexity and simplifies cross-collection references

**Index-first approach:**
- Indexes designed and created before implementing queries
- All compound indexes place `tenant_id` first for multi-tenant isolation
- Unique constraint on `(tenant_id, external_id)` enforces idempotency at the database level

**Atomic lock acquisition:**
- Single `find_one_and_update` operation with `upsert=True`
- Eliminates check-then-act race conditions
- Lock expiration (60s TTL) prevents deadlocks from crashed processes

**Aggregation-first analytics:**
- All metrics computed server-side using MongoDB aggregation pipelines
- `$facet` stage enables parallel computation of multiple metrics in a single query
- Zero Python-side iteration over raw documents

**Minimal external dependencies:**
- No retry libraries (tenacity, backoff)
- No distributed lock libraries (redis-lock, pottery)
- No circuit breaker libraries (pybreaker)
- Custom implementations using standard library primitives

---

## Trade-offs & Prioritization

**Prioritized (critical path):**
- Manual pagination
- Idempotent ingestion
- Per-tenant locking
- Database-centric analytics

**Deprioritized / intentionally simplified:**
- Advanced classification logic (kept rule-based)
- Background workers or async queues
- External retry / lock libraries
- Authentication and authorization

These choices were made to focus on correctness, concurrency safety, and system design.


---

## Running the Project

```bash
# 1. Copy environment variables
cp .env.example .env

# 2. Start services
docker compose up --build
```
