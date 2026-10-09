"""Shared rate limiter instance (imported by main and routers)."""
from slowapi import Limiter
from slowapi.util import get_remote_address

# NOTE: the default in-memory store is per-process. For multi-worker or
# multi-container deployments, point storage_uri at Redis.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300/hour"],
)