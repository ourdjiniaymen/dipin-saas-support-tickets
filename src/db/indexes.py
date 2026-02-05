from src.db.mongo import get_db
import pymongo


async def create_indexes():
    """
    Create MongoDB indexes required for common query patterns and to keep
    the dataset manageable over time (e.g. compound indexes, unique
    constraints, TTL on old data).
    """
    db = await get_db()
    tickets = db.tickets

     # 🐛 DEBUG TASK E: Inefficient indexes
    # The indexes below are intentionally misaligned with real query
    # patterns and will cause performance issues.
    # ============================================================

    # Index 1 — Idempotency
    await tickets.create_index(
        [("tenant_id", pymongo.ASCENDING), ("external_id", pymongo.ASCENDING)],
        unique=True,
        name="idx_tenant_external_unique"
    )

    # Index 2 - Stats / Listing
    await tickets.create_index(
        [("tenant_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
        name="idx_tenant_created"
    )

    # Index 3 - Status Filterd Stats
    await tickets.create_index(
        [
            ("tenant_id", pymongo.ASCENDING),
            ("status", pymongo.ASCENDING),
            ("created_at", pymongo.DESCENDING)
        ],
        name="idx_tenant_status_created"
    )
    
    # Index 4: urgency for analytics
    await tickets.create_index(
        [("tenant_id", pymongo.ASCENDING), ("urgency", pymongo.ASCENDING)],
        name="idx_tenant_urgency"
    )

    # Index 5: soft delete filtering
    await tickets.create_index(
        [("tenant_id", pymongo.ASCENDING), ("deleted_at", pymongo.ASCENDING)],
        name="idx_tenant_deleted"
    )




    

    # ingestion_jobs 컬렉션 인덱스
    ingestion_jobs = db.ingestion_jobs
    await ingestion_jobs.create_index([("tenant_id", pymongo.ASCENDING)])
    await ingestion_jobs.create_index([("status", pymongo.ASCENDING)])

    # ingestion_logs 컬렉션 인덱스
    ingestion_logs = db.ingestion_logs
    await ingestion_logs.create_index([("tenant_id", pymongo.ASCENDING)])
    await ingestion_logs.create_index([("job_id", pymongo.ASCENDING)])


# ============================================================
# Hint: Example of good index design
# ============================================================
# The commented-out indexes below illustrate better patterns.
# To address Debug Task E, replace the inefficient indexes above
# with indexes that follow these patterns.
#
# # Unique index for idempotency
# await tickets.create_index(
#     [("tenant_id", pymongo.ASCENDING), ("external_id", pymongo.ASCENDING)],
#     unique=True
# )
#
# # Efficient composite index (tenant_id first, then created_at)
# await tickets.create_index([
#     ("tenant_id", pymongo.ASCENDING),
#     ("created_at", pymongo.DESCENDING)
# ])
#
# # Composite index for multi-condition queries
# await tickets.create_index([
#     ("tenant_id", pymongo.ASCENDING),
#     ("status", pymongo.ASCENDING),
#     ("created_at", pymongo.DESCENDING)
# ])
#
# # TTL index (automatic cleanup of old data)
# await tickets.create_index(
#     [("created_at", pymongo.ASCENDING)],
#     expireAfterSeconds=60 * 60 * 24 * 90  # 90 days
# )
