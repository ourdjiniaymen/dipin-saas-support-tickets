from datetime import datetime, timedelta
from src.db.mongo import get_db


class AnalyticsService:
    async def get_tenant_stats(
        self,
        tenant_id: str,
        from_date: datetime = None,
        to_date: datetime = None
    ) -> dict:
        """
        Compute analytics for a tenant within a date range.
        All heavy computation is performed inside MongoDB.
        """
        db = await get_db()

        # Default to last 24 hours
        if not to_date:
            to_date = datetime.utcnow()
        if not from_date:
            from_date = to_date - timedelta(hours=24)

        pipeline = [
            # Stage 1: Filter by tenant and exclude soft-deleted tickets
            {
                "$match": {
                    "tenant_id": tenant_id,
                    "deleted_at": None
                }
            },

            # Stage 2: Parallel aggregations
            {
                "$facet": {
                    "total": [
                        {"$count": "count"}
                    ],

                    "by_status": [
                        {
                            "$group": {
                                "_id": "$status",
                                "count": {"$sum": 1}
                            }
                        }
                    ],

                    "by_urgency": [
                        {
                            "$group": {
                                "_id": "$urgency",
                                "count": {"$sum": 1}
                            }
                        }
                    ],

                    "hourly_trend": [
                        {
                            "$match": {
                                "created_at": {
                                    "$gte": from_date,
                                    "$lte": to_date
                                }
                            }
                        },
                        {
                            "$group": {
                                "_id": {
                                    "$dateToString": {
                                        "format": "%Y-%m-%d %H:00",
                                        "date": "$created_at"
                                    }
                                },
                                "count": {"$sum": 1}
                            }
                        },
                        {"$sort": {"_id": 1}}
                    ]
                }
            },

            # Stage 3: Shape final output
            {
                "$project": {
                    "total_tickets": {
                        "$ifNull": [
                            {"$arrayElemAt": ["$total.count", 0]},
                            0
                        ]
                    },

                    "by_status": {
                        "$arrayToObject": {
                            "$map": {
                                "input": "$by_status",
                                "as": "item",
                                "in": {
                                    "k": "$$item._id",
                                    "v": "$$item.count"
                                }
                            }
                        }
                    },

                    "urgency_high_ratio": {
                        "$cond": {
                            "if": {
                                "$gt": [
                                    {"$arrayElemAt": ["$total.count", 0]},
                                    0
                                ]
                            },
                            "then": {
                                "$divide": [
                                    {
                                        "$reduce": {
                                            "input": "$by_urgency",
                                            "initialValue": 0,
                                            "in": {
                                                "$cond": {
                                                    "if": {
                                                        "$eq": ["$$this._id", "high"]
                                                    },
                                                    "then": {
                                                        "$add": [
                                                            "$$value",
                                                            "$$this.count"
                                                        ]
                                                    },
                                                    "else": "$$value"
                                                }
                                            }
                                        }
                                    },
                                    {"$arrayElemAt": ["$total.count", 0]}
                                ]
                            },
                            "else": 0.0
                        }
                    },

                    "hourly_trend": {
                        "$map": {
                            "input": "$hourly_trend",
                            "as": "item",
                            "in": {
                                "hour": "$$item._id",
                                "count": "$$item.count"
                            }
                        }
                    }
                }
            }
        ]

        cursor = db.tickets.aggregate(pipeline)
        results = await cursor.to_list(length=1)

        if not results:
            return {
                "total_tickets": 0,
                "by_status": {},
                "urgency_high_ratio": 0.0,
                "hourly_trend": []
            }

        return results[0]
