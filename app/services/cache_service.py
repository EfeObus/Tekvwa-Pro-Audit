"""
Tekvwa Pro Audit - Cache Service

Redis-based caching service for performance optimization.
Provides caching for:
- Exchange rates (FX)
- Consolidated trial balances
- Report data
- User sessions

Author: Tekvwa Pro Audit Team
Date: January 2026
"""

import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional, Dict, List, Union
from functools import wraps

import redis.asyncio as redis
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CacheService:
    """Redis-based caching service."""
    
    # Cache key prefixes
    PREFIX_FX_RATE = "fx:rate"
    PREFIX_FX_RATES_ALL = "fx:rates:all"
    PREFIX_CONSOLIDATED_TB = "consolidation:tb"
    PREFIX_REPORT = "report"
    PREFIX_USER_SESSION = "session"
    PREFIX_TENANT = "tenant"
    
    # Default TTL values (in seconds)
    TTL_FX_RATE = 3600  # 1 hour - rates change daily
    TTL_FX_RATES_ALL = 1800  # 30 minutes
    TTL_CONSOLIDATED_TB = 300  # 5 minutes - complex calculation
    TTL_REPORT = 900  # 15 minutes
    TTL_SESSION = 86400  # 24 hours
    TTL_TENANT = 3600  # 1 hour
    
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.redis_url
        self._client: Optional[redis.Redis] = None
        
    async def get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client
    
    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
    
    # =========================================================================
    # GENERIC CACHE OPERATIONS
    # =========================================================================
    
    async def get(self, key: str) -> Optional[str]:
        """Get a value from cache."""
        try:
            client = await self.get_client()
            return await client.get(key)
        except Exception as e:
            logger.warning(f"Cache get failed for {key}: {e}")
            return None
    
    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a value in cache with optional TTL."""
        try:
            client = await self.get_client()
            if ttl:
                await client.setex(key, ttl, value)
            else:
                await client.set(key, value)
            return True
        except Exception as e:
            logger.warning(f"Cache set failed for {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        try:
            client = await self.get_client()
            await client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete failed for {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern."""
        try:
            client = await self.get_client()
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                return await client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Cache delete_pattern failed for {pattern}: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        try:
            client = await self.get_client()
            return await client.exists(key) > 0
        except Exception as e:
            logger.warning(f"Cache exists check failed for {key}: {e}")
            return False
    
    async def get_json(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a JSON value from cache."""
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in cache for {key}")
        return None
    
    async def set_json(
        self,
        key: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a JSON value in cache."""
        try:
            return await self.set(key, json.dumps(value, default=str), ttl)
        except Exception as e:
            logger.warning(f"Cache set_json failed for {key}: {e}")
            return False
    
    # =========================================================================
    # FX RATE CACHING
    # =========================================================================
    
    def _fx_rate_key(
        self,
        from_currency: str,
        to_currency: str,
        rate_date: date,
    ) -> str:
        """Generate cache key for FX rate."""
        return f"{self.PREFIX_FX_RATE}:{from_currency}:{to_currency}:{rate_date.isoformat()}"
    
    def _fx_rates_all_key(
        self,
        base_currency: str,
        rate_date: date,
    ) -> str:
        """Generate cache key for all FX rates."""
        return f"{self.PREFIX_FX_RATES_ALL}:{base_currency}:{rate_date.isoformat()}"
    
    async def get_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate_date: date,
    ) -> Optional[Decimal]:
        """Get cached FX rate."""
        key = self._fx_rate_key(from_currency, to_currency, rate_date)
        value = await self.get(key)
        if value:
            try:
                return Decimal(value)
            except Exception:
                pass
        return None
    
    async def set_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate_date: date,
        rate: Decimal,
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache an FX rate."""
        key = self._fx_rate_key(from_currency, to_currency, rate_date)
        return await self.set(key, str(rate), ttl or self.TTL_FX_RATE)
    
    async def get_all_fx_rates(
        self,
        base_currency: str,
        rate_date: date,
    ) -> Optional[Dict[str, Decimal]]:
        """Get cached FX rates for all currencies to base."""
        key = self._fx_rates_all_key(base_currency, rate_date)
        data = await self.get_json(key)
        if data:
            return {k: Decimal(v) for k, v in data.items()}
        return None
    
    async def set_all_fx_rates(
        self,
        base_currency: str,
        rate_date: date,
        rates: Dict[str, Decimal],
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache all FX rates to base currency."""
        key = self._fx_rates_all_key(base_currency, rate_date)
        data = {k: str(v) for k, v in rates.items()}
        return await self.set_json(key, data, ttl or self.TTL_FX_RATES_ALL)
    
    async def invalidate_fx_rates(
        self,
        from_currency: Optional[str] = None,
        to_currency: Optional[str] = None,
    ) -> int:
        """Invalidate cached FX rates."""
        if from_currency and to_currency:
            pattern = f"{self.PREFIX_FX_RATE}:{from_currency}:{to_currency}:*"
        elif from_currency:
            pattern = f"{self.PREFIX_FX_RATE}:{from_currency}:*"
        else:
            pattern = f"{self.PREFIX_FX_RATE}:*"
        
        count = await self.delete_pattern(pattern)
        # Also invalidate "all rates" cache
        count += await self.delete_pattern(f"{self.PREFIX_FX_RATES_ALL}:*")
        return count
    
    # =========================================================================
    # CONSOLIDATION CACHING
    # =========================================================================
    
    def _consolidated_tb_key(
        self,
        parent_entity_id: str,
        as_of_date: date,
        include_eliminations: bool,
    ) -> str:
        """Generate cache key for consolidated trial balance."""
        elim_flag = "with_elim" if include_eliminations else "no_elim"
        return f"{self.PREFIX_CONSOLIDATED_TB}:{parent_entity_id}:{as_of_date.isoformat()}:{elim_flag}"
    
    async def get_consolidated_tb(
        self,
        parent_entity_id: str,
        as_of_date: date,
        include_eliminations: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Get cached consolidated trial balance."""
        key = self._consolidated_tb_key(parent_entity_id, as_of_date, include_eliminations)
        return await self.get_json(key)
    
    async def set_consolidated_tb(
        self,
        parent_entity_id: str,
        as_of_date: date,
        include_eliminations: bool,
        data: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache consolidated trial balance."""
        key = self._consolidated_tb_key(parent_entity_id, as_of_date, include_eliminations)
        return await self.set_json(key, data, ttl or self.TTL_CONSOLIDATED_TB)
    
    async def invalidate_consolidation(
        self,
        parent_entity_id: Optional[str] = None,
    ) -> int:
        """Invalidate consolidation cache."""
        if parent_entity_id:
            pattern = f"{self.PREFIX_CONSOLIDATED_TB}:{parent_entity_id}:*"
        else:
            pattern = f"{self.PREFIX_CONSOLIDATED_TB}:*"
        return await self.delete_pattern(pattern)
    
    # =========================================================================
    # REPORT CACHING
    # =========================================================================
    
    def _report_key(
        self,
        report_type: str,
        tenant_id: str,
        params_hash: str,
    ) -> str:
        """Generate cache key for report."""
        return f"{self.PREFIX_REPORT}:{report_type}:{tenant_id}:{params_hash}"
    
    async def get_report(
        self,
        report_type: str,
        tenant_id: str,
        params_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """Get cached report data."""
        key = self._report_key(report_type, tenant_id, params_hash)
        return await self.get_json(key)
    
    async def set_report(
        self,
        report_type: str,
        tenant_id: str,
        params_hash: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache report data."""
        key = self._report_key(report_type, tenant_id, params_hash)
        return await self.set_json(key, data, ttl or self.TTL_REPORT)
    
    async def invalidate_reports(
        self,
        tenant_id: Optional[str] = None,
        report_type: Optional[str] = None,
    ) -> int:
        """Invalidate report cache."""
        if tenant_id and report_type:
            pattern = f"{self.PREFIX_REPORT}:{report_type}:{tenant_id}:*"
        elif tenant_id:
            pattern = f"{self.PREFIX_REPORT}:*:{tenant_id}:*"
        elif report_type:
            pattern = f"{self.PREFIX_REPORT}:{report_type}:*"
        else:
            pattern = f"{self.PREFIX_REPORT}:*"
        return await self.delete_pattern(pattern)
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    async def health_check(self) -> Dict[str, Any]:
        """Check cache health."""
        try:
            client = await self.get_client()
            await client.ping()
            info = await client.info()
            return {
                "status": "healthy",
                "connected": True,
                "used_memory": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e),
            }
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            client = await self.get_client()
            info = await client.info()
            
            # Count keys by prefix
            fx_count = 0
            consolidation_count = 0
            report_count = 0
            
            async for _ in client.scan_iter(match=f"{self.PREFIX_FX_RATE}:*"):
                fx_count += 1
            async for _ in client.scan_iter(match=f"{self.PREFIX_CONSOLIDATED_TB}:*"):
                consolidation_count += 1
            async for _ in client.scan_iter(match=f"{self.PREFIX_REPORT}:*"):
                report_count += 1
            
            return {
                "total_keys": info.get("db0", {}).get("keys", 0),
                "fx_rate_keys": fx_count,
                "consolidation_keys": consolidation_count,
                "report_keys": report_count,
                "memory_used": info.get("used_memory_human", "unknown"),
                "hit_rate": f"{info.get('keyspace_hits', 0) / max(1, info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0)) * 100:.2f}%",
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def clear_all(self) -> bool:
        """Clear all cache (use with caution!)."""
        try:
            client = await self.get_client()
            await client.flushdb()
            logger.info("Cache cleared successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False


# =========================================================================
# GLOBAL CACHE INSTANCE
# =========================================================================

_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get global cache service instance."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service


async def close_cache_service():
    """Close global cache service."""
    global _cache_service
    if _cache_service:
        await _cache_service.close()
        _cache_service = None


# =========================================================================
# DECORATORS FOR CACHING
# =========================================================================

def cached_fx_rate(ttl: int = CacheService.TTL_FX_RATE):
    """
    Decorator to cache FX rate lookups.
    
    Usage:
        @cached_fx_rate()
        async def get_exchange_rate(self, from_currency, to_currency, rate_date):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(
            self,
            from_currency: str,
            to_currency: str,
            rate_date: Optional[date] = None,
            *args,
            **kwargs,
        ):
            # Don't cache same currency conversions
            if from_currency == to_currency:
                return Decimal("1.000000")
            
            if rate_date is None:
                rate_date = date.today()
            
            cache = get_cache_service()
            
            # Try cache first
            cached = await cache.get_fx_rate(from_currency, to_currency, rate_date)
            if cached is not None:
                return cached
            
            # Get from database
            result = await func(self, from_currency, to_currency, rate_date, *args, **kwargs)
            
            # Cache the result
            if result is not None:
                await cache.set_fx_rate(from_currency, to_currency, rate_date, result, ttl)
            
            return result
        return wrapper
    return decorator


def cached_consolidation(ttl: int = CacheService.TTL_CONSOLIDATED_TB):
    """
    Decorator to cache consolidated trial balance calculations.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(
            self,
            parent_entity_id: str,
            as_of_date: date,
            include_eliminations: bool = True,
            *args,
            **kwargs,
        ):
            cache = get_cache_service()
            
            # Try cache first
            cached = await cache.get_consolidated_tb(
                parent_entity_id, as_of_date, include_eliminations
            )
            if cached is not None:
                return cached
            
            # Calculate
            result = await func(
                self, parent_entity_id, as_of_date, include_eliminations, *args, **kwargs
            )
            
            # Cache the result
            if result is not None:
                await cache.set_consolidated_tb(
                    parent_entity_id, as_of_date, include_eliminations, result, ttl
                )
            
            return result
        return wrapper
    return decorator
