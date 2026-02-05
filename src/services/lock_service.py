"""
Task 8: Distributed lock service.

Implement a distributed lock using MongoDB atomic operations.
Do not use external distributed lock libraries (redis-lock, pottery, etc.).

Requirements:
1. Prevent concurrent ingestion for the same tenant.
2. Return 409 Conflict when lock acquisition fails.
3. Automatically release locks when they are not refreshed within 60 seconds (zombie lock prevention).
4. Provide lock status inspection APIs.
"""

from datetime import datetime, timedelta
from typing import Optional
from src.db.mongo import get_db
from pymongo import ReturnDocument


class LockService:
    """
    MongoDB-based distributed lock service.

    Hints:
    - Use `findOneAndUpdate` with `upsert` to acquire locks.
    - Use TTL-like behaviour for automatic expiration.
    - Acquire/release locks atomically.
    """

    LOCK_COLLECTION = "distributed_locks"
    LOCK_TTL_SECONDS = 60

    async def acquire_lock(self, resource_id: str, owner_id: str) -> bool:
        """
        Attempt to acquire a lock.

        Args:
            resource_id: ID of the resource to lock (e.g., tenant_id).
            owner_id: Lock owner identifier (e.g., job_id).

        Returns:
            True if lock acquired, False otherwise.
        """
        db = await get_db()
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=self.LOCK_TTL_SECONDS)

        try:
            result = await db[self.LOCK_COLLECTION].find_one_and_update(
                {
                    "resource_id": resource_id,
                    "$or": [
                        {"locked": {"$ne": True}},
                        {"expires_at": {"$lt": now}}
                    ]
                },
                {
                    "$set": {
                        "resource_id": resource_id,
                        "locked": True,
                        "owner_id": owner_id,
                        "acquired_at": now,
                        "expires_at": expires_at
                    }
                },
                upsert=True,
                return_document=ReturnDocument.AFTER
            )
            return result and result.get("owner_id") == owner_id
        except Exception:
            return False

    async def release_lock(self, resource_id: str, owner_id: str) -> bool:
        """
        Release a lock.

        Args:
            resource_id: ID of the resource to unlock.
            owner_id: Lock owner identifier (only the owner may release).

        Returns:
            True if lock released, False otherwise.
        """
        db = await get_db()
        result = await db[self.LOCK_COLLECTION].update_one(
            {"resource_id": resource_id, "owner_id": owner_id},
            {"$set": {"locked": False}}
        )
        return result.modified_count > 0

    async def refresh_lock(self, resource_id: str, owner_id: str) -> bool:
        """
        Refresh a lock's TTL to prevent expiration.

        Args:
            resource_id: ID of the lock to refresh.
            owner_id: Lock owner identifier.

        Returns:
            True if lock refreshed, False otherwise.
        """
        
        db = await get_db()
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=self.LOCK_TTL_SECONDS)
        result = await db[self.LOCK_COLLECTION].update_one(
            {"resource_id": resource_id, "owner_id": owner_id, "locked": True},
            {"$set": {"expires_at": expires_at}}
        )
        return result.modified_count > 0

    async def get_lock_status(self, resource_id: str) -> Optional[dict]:
        """
        Get current lock status for a resource.

        Returns:
            A dict describing the lock or None if no lock exists:
            {
                "resource_id": str,
                "owner_id": str,
                "acquired_at": datetime,
                "expires_at": datetime,
                "is_expired": bool
            }
        """
        db = await get_db()
        lock = await db[self.LOCK_COLLECTION].find_one({"resource_id": resource_id})

        if not lock:
            return None

        now = datetime.utcnow()
        expires_at = lock.get("expires_at", now)

        return {
            "resource_id": lock["resource_id"],
            "owner_id": lock["owner_id"],
            "acquired_at": lock.get("acquired_at"),
            "expires_at": expires_at,
            "is_expired": now > expires_at
        }

    async def cleanup_expired_locks(self) -> int:
        """
        Clean up expired locks (optional helper).

        Returns:
            Number of deleted locks.
        """
        db = await get_db()
        result = await db[self.LOCK_COLLECTION].delete_many({
            "expires_at": {"$lt": datetime.utcnow()}
        })
        return result.deleted_count
