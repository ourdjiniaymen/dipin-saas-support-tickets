from typing import List, Optional
from datetime import datetime
import httpx
import asyncio
from src.db.mongo import get_db
from src.services.classify_service import ClassifyService
from src.services.notify_service import NotifyService

# ============================================================
# 🐛 DEBUG TASK C: Memory leak
# This cache is never cleared.
# New data is appended on every ingestion run.
# ============================================================
_ingestion_cache = {}


class IngestService:
    def __init__(self):
        self.external_api_url = "http://mock-external-api:9000/external/support-tickets"
        self.classify_service = ClassifyService()
        self.notify_service = NotifyService()

    async def run_ingestion(self, tenant_id: str) -> dict:
        """
        Fetch tickets from the external API and persist them for a tenant.
        The implementation should take into account pagination, duplicate
        handling, ticket classification and any side effects such as
        notifications and logging.
        """
        db = await get_db()

        # ============================================================
        # 🐛 DEBUG TASK D: Race condition
        # Check-then-act pattern: concurrent requests can both pass.
        # ============================================================
        existing_job = await db.ingestion_jobs.find_one({
            "tenant_id": tenant_id,
            "status": "running"
        })

        # 🐛 If a context switch happens here, multiple requests can pass this point.
        await asyncio.sleep(0)  # intentional yield point

        if existing_job:
            return {
                "status": "already_running",
                "job_id": str(existing_job["_id"]),
                "new_ingested": 0,
                "updated": 0,
                "errors": 0
            }

        # Record ingestion job start
        job_doc = {
            "tenant_id": tenant_id,
            "status": "running",
            "started_at": datetime.utcnow(),
            "progress": 0,
            "total_pages": None,
            "processed_pages": 0
        }
        result = await db.ingestion_jobs.insert_one(job_doc)
        job_id = str(result.inserted_id)

        # ============================================================
        # 🐛 DEBUG TASK C: Memory leak (continued)
        # On every ingestion run, entries are added to the cache and never removed.
        # ============================================================
        cache_key = f"{tenant_id}_{datetime.utcnow().isoformat()}"
        _ingestion_cache[cache_key] = {
            "job_id": job_id,
            "tickets": [],  # All ingested tickets are appended to this list
            "started_at": datetime.utcnow()
        }

        # TODO: implement ingestion behaviour
        # - Handle pagination
        # - Guarantee idempotency (upsert)
        # - Invoke classification service
        # - Invoke notification service for high-urgency tickets
        # - Handle rate limiting (wait on 429 + Retry-After)

        new_ingested = 0
        updated = 0
        errors = 0

        try:
            # Implement the actual ingestion logic here.
            # Hint: use httpx.AsyncClient, a pagination loop, and upserts.

            # 🐛 Memory leak: all tickets are stored in the cache.
            # _ingestion_cache[cache_key]["tickets"].append(ticket_data)

            pass

        except Exception as e:
            # Always log failures
            await db.ingestion_logs.insert_one({
                "tenant_id": tenant_id,
                "job_id": job_id,
                "status": "failed",
                "error": str(e),
                "started_at": job_doc["started_at"],
                "ended_at": datetime.utcnow(),
                "new_ingested": new_ingested,
                "updated": updated,
                "errors": errors
            })
            raise

        # Log successful completion
        await db.ingestion_jobs.update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": "completed", "ended_at": datetime.utcnow()}}
        )

        await db.ingestion_logs.insert_one({
            "tenant_id": tenant_id,
            "job_id": job_id,
            "status": "completed",
            "started_at": job_doc["started_at"],
            "ended_at": datetime.utcnow(),
            "new_ingested": new_ingested,
            "updated": updated,
            "errors": errors
        })

        return {
            "status": "completed",
            "job_id": job_id,
            "new_ingested": new_ingested,
            "updated": updated,
            "errors": errors
        }

    async def get_job_status(self, job_id: str) -> Optional[dict]:
        """Retrieve the status of a specific ingestion job."""
        db = await get_db()
        from bson import ObjectId

        job = await db.ingestion_jobs.find_one({"_id": ObjectId(job_id)})
        if not job:
            return None

        return {
            "job_id": job_id,
            "tenant_id": job["tenant_id"],
            "status": job["status"],
            "progress": job.get("progress", 0),
            "total_pages": job.get("total_pages"),
            "processed_pages": job.get("processed_pages", 0),
            "started_at": job["started_at"].isoformat() if job.get("started_at") else None,
            "ended_at": job["ended_at"].isoformat() if job.get("ended_at") else None
        }

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel an ongoing ingestion job, if it is still running."""
        db = await get_db()
        from bson import ObjectId

        result = await db.ingestion_jobs.update_one(
            {"_id": ObjectId(job_id), "status": "running"},
            {"$set": {"status": "cancelled", "ended_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    async def get_ingestion_status(self, tenant_id: str) -> Optional[dict]:
        """Get the current ingestion status for a given tenant."""
        db = await get_db()

        job = await db.ingestion_jobs.find_one(
            {"tenant_id": tenant_id, "status": "running"},
            sort=[("started_at", -1)]
        )

        if not job:
            return None

        return {
            "job_id": str(job["_id"]),
            "tenant_id": tenant_id,
            "status": job["status"],
            "started_at": job["started_at"].isoformat() if job.get("started_at") else None
        }
