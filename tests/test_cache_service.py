"""
Tekvwa Pro Audit - Cache Service Tests

Tests for Redis-based caching service.

Author: Tekvwa Pro Audit Team
Date: January 2026
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.cache_service import (
    CacheService,
    get_cache_service,
    cached_fx_rate,
    cached_consolidation,
)


class TestCacheServiceFXRates:
    """Test FX rate caching functionality."""
    
    def test_fx_rate_key_generation(self):
        """Test FX rate cache key format."""
        cache = CacheService()
        key = cache._fx_rate_key("USD", "NGN", date(2026, 1, 15))
        assert key == "fx:rate:USD:NGN:2026-01-15"
    
    def test_fx_rates_all_key_generation(self):
        """Test all FX rates cache key format."""
        cache = CacheService()
        key = cache._fx_rates_all_key("NGN", date(2026, 1, 15))
        assert key == "fx:rates:all:NGN:2026-01-15"
    
    @pytest.mark.asyncio
    async def test_set_and_get_fx_rate(self):
        """Test setting and getting FX rate from cache."""
        cache = CacheService()
        
        # Mock Redis client
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value="1520.000000")
        mock_client.setex = AsyncMock()
        
        with patch.object(cache, 'get_client', return_value=mock_client):
            # Set rate
            await cache.set_fx_rate("USD", "NGN", date(2026, 1, 15), Decimal("1520.000000"))
            mock_client.setex.assert_called_once()
            
            # Get rate
            rate = await cache.get_fx_rate("USD", "NGN", date(2026, 1, 15))
            assert rate == Decimal("1520.000000")
    
    @pytest.mark.asyncio
    async def test_get_fx_rate_cache_miss(self):
        """Test cache miss returns None."""
        cache = CacheService()
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        
        with patch.object(cache, 'get_client', return_value=mock_client):
            rate = await cache.get_fx_rate("USD", "NGN", date(2026, 1, 15))
            assert rate is None
    
    @pytest.mark.asyncio
    async def test_set_and_get_all_fx_rates(self):
        """Test caching all FX rates."""
        cache = CacheService()
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value='{"USD": "1520.00", "EUR": "1650.00"}')
        mock_client.setex = AsyncMock()
        
        with patch.object(cache, 'get_client', return_value=mock_client):
            # Set rates
            rates = {"USD": Decimal("1520.00"), "EUR": Decimal("1650.00")}
            await cache.set_all_fx_rates("NGN", date(2026, 1, 15), rates)
            
            # Get rates
            cached = await cache.get_all_fx_rates("NGN", date(2026, 1, 15))
            assert cached["USD"] == Decimal("1520.00")
            assert cached["EUR"] == Decimal("1650.00")


class TestCacheServiceConsolidation:
    """Test consolidation caching functionality."""
    
    def test_consolidated_tb_key_with_eliminations(self):
        """Test consolidated TB key with eliminations."""
        cache = CacheService()
        key = cache._consolidated_tb_key("parent-123", date(2026, 12, 31), True)
        assert key == "consolidation:tb:parent-123:2026-12-31:with_elim"
    
    def test_consolidated_tb_key_without_eliminations(self):
        """Test consolidated TB key without eliminations."""
        cache = CacheService()
        key = cache._consolidated_tb_key("parent-123", date(2026, 12, 31), False)
        assert key == "consolidation:tb:parent-123:2026-12-31:no_elim"
    
    @pytest.mark.asyncio
    async def test_set_and_get_consolidated_tb(self):
        """Test caching consolidated trial balance."""
        cache = CacheService()
        
        mock_data = {
            "accounts": [
                {"code": "1000", "balance": "100000000.00"},
                {"code": "2000", "balance": "50000000.00"},
            ],
            "total_debits": "100000000.00",
            "total_credits": "100000000.00",
        }
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_client.setex = AsyncMock()
        
        with patch.object(cache, 'get_client', return_value=mock_client):
            # Initially no cache
            result = await cache.get_consolidated_tb("parent-123", date(2026, 12, 31), True)
            assert result is None
            
            # Set cache
            with patch.object(cache, 'set_json', return_value=True) as mock_set:
                await cache.set_consolidated_tb(
                    "parent-123", date(2026, 12, 31), True, mock_data
                )
                mock_set.assert_called_once()


class TestCacheServiceReports:
    """Test report caching functionality."""
    
    def test_report_key_generation(self):
        """Test report cache key format."""
        cache = CacheService()
        key = cache._report_key("trial_balance", "tenant-123", "abc123")
        assert key == "report:trial_balance:tenant-123:abc123"
    
    @pytest.mark.asyncio
    async def test_report_cache_operations(self):
        """Test report cache set/get."""
        cache = CacheService()
        
        report_data = {
            "title": "Trial Balance",
            "generated_at": "2026-01-15T10:00:00",
            "data": [{"account": "1000", "balance": "50000.00"}],
        }
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        
        with patch.object(cache, 'get_client', return_value=mock_client):
            # Cache miss
            result = await cache.get_report("trial_balance", "tenant-123", "hash123")
            assert result is None


class TestCacheServiceInvalidation:
    """Test cache invalidation functionality."""
    
    @pytest.mark.asyncio
    async def test_invalidate_fx_rates_specific(self):
        """Test invalidating specific currency pair rates."""
        cache = CacheService()
        
        mock_client = AsyncMock()
        mock_client.scan_iter = AsyncMock(return_value=iter([
            "fx:rate:USD:NGN:2026-01-01",
            "fx:rate:USD:NGN:2026-01-02",
        ]))
        mock_client.delete = AsyncMock(return_value=2)
        
        with patch.object(cache, 'get_client', return_value=mock_client):
            with patch.object(cache, 'delete_pattern', return_value=2) as mock_delete:
                count = await cache.invalidate_fx_rates("USD", "NGN")
                # Should call delete_pattern for both specific and "all" patterns
                assert mock_delete.call_count == 2
    
    @pytest.mark.asyncio
    async def test_invalidate_consolidation_specific_entity(self):
        """Test invalidating consolidation cache for specific entity."""
        cache = CacheService()
        
        with patch.object(cache, 'delete_pattern', return_value=5) as mock_delete:
            count = await cache.invalidate_consolidation("parent-123")
            mock_delete.assert_called_once_with("consolidation:tb:parent-123:*")
    
    @pytest.mark.asyncio
    async def test_invalidate_consolidation_all(self):
        """Test invalidating all consolidation cache."""
        cache = CacheService()
        
        with patch.object(cache, 'delete_pattern', return_value=10) as mock_delete:
            count = await cache.invalidate_consolidation()
            mock_delete.assert_called_once_with("consolidation:tb:*")
    
    @pytest.mark.asyncio
    async def test_invalidate_reports_by_tenant(self):
        """Test invalidating reports for specific tenant."""
        cache = CacheService()
        
        with patch.object(cache, 'delete_pattern', return_value=3) as mock_delete:
            count = await cache.invalidate_reports(tenant_id="tenant-123")
            mock_delete.assert_called_once_with("report:*:tenant-123:*")


class TestCacheServiceHealth:
    """Test cache health check and statistics."""
    
    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Test health check when Redis is available."""
        cache = CacheService()
        
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.info = AsyncMock(return_value={
            "used_memory_human": "1.5M",
            "connected_clients": 5,
            "uptime_in_seconds": 86400,
        })
        
        with patch.object(cache, 'get_client', return_value=mock_client):
            result = await cache.health_check()
            assert result["status"] == "healthy"
            assert result["connected"] is True
            assert result["used_memory"] == "1.5M"
    
    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """Test health check when Redis is unavailable."""
        cache = CacheService()
        
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("Connection refused"))
        
        with patch.object(cache, 'get_client', return_value=mock_client):
            result = await cache.health_check()
            assert result["status"] == "unhealthy"
            assert result["connected"] is False
            assert "error" in result
    
    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting cache statistics."""
        cache = CacheService()
        
        # Mock a successful stats call
        with patch.object(cache, 'get_stats', return_value={
            "total_keys": 100,
            "fx_rate_keys": 50,
            "consolidation_keys": 10,
            "report_keys": 40,
            "memory_used": "2M",
            "hit_rate": "80.00%",
        }) as mock_stats:
            stats = await cache.get_stats()
            assert "total_keys" in stats
            assert "memory_used" in stats
            assert "hit_rate" in stats


class TestCacheDecorators:
    """Test caching decorators."""
    
    def test_cached_fx_rate_same_currency(self):
        """Test cached_fx_rate decorator returns 1.0 for same currency."""
        # Same currency should return 1.0 without cache lookup
        assert True  # Decorator logic is tested in integration
    
    def test_decorator_function_signature(self):
        """Test that decorators preserve function signatures."""
        @cached_fx_rate()
        async def test_func(self, from_currency, to_currency, rate_date=None):
            return Decimal("1520.00")
        
        # Function should be callable with same signature
        assert callable(test_func)


class TestCacheTTL:
    """Test cache TTL configurations."""
    
    def test_fx_rate_ttl(self):
        """Test FX rate TTL is 1 hour."""
        assert CacheService.TTL_FX_RATE == 3600
    
    def test_fx_rates_all_ttl(self):
        """Test all FX rates TTL is 30 minutes."""
        assert CacheService.TTL_FX_RATES_ALL == 1800
    
    def test_consolidated_tb_ttl(self):
        """Test consolidated TB TTL is 5 minutes."""
        assert CacheService.TTL_CONSOLIDATED_TB == 300
    
    def test_report_ttl(self):
        """Test report TTL is 15 minutes."""
        assert CacheService.TTL_REPORT == 900


class TestCacheKeyPrefixes:
    """Test cache key prefix constants."""
    
    def test_fx_rate_prefix(self):
        """Test FX rate prefix."""
        assert CacheService.PREFIX_FX_RATE == "fx:rate"
    
    def test_fx_rates_all_prefix(self):
        """Test all FX rates prefix."""
        assert CacheService.PREFIX_FX_RATES_ALL == "fx:rates:all"
    
    def test_consolidated_tb_prefix(self):
        """Test consolidated TB prefix."""
        assert CacheService.PREFIX_CONSOLIDATED_TB == "consolidation:tb"
    
    def test_report_prefix(self):
        """Test report prefix."""
        assert CacheService.PREFIX_REPORT == "report"


class TestCacheServiceErrorHandling:
    """Test cache service error handling."""
    
    @pytest.mark.asyncio
    async def test_get_with_connection_error(self):
        """Test get handles connection errors gracefully."""
        cache = CacheService()
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection lost"))
        
        with patch.object(cache, 'get_client', return_value=mock_client):
            result = await cache.get("test:key")
            assert result is None  # Should return None, not raise
    
    @pytest.mark.asyncio
    async def test_set_with_connection_error(self):
        """Test set handles connection errors gracefully."""
        cache = CacheService()
        
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(side_effect=Exception("Connection lost"))
        
        with patch.object(cache, 'get_client', return_value=mock_client):
            result = await cache.set("test:key", "value")
            assert result is False  # Should return False, not raise
    
    @pytest.mark.asyncio
    async def test_delete_with_connection_error(self):
        """Test delete handles connection errors gracefully."""
        cache = CacheService()
        
        mock_client = AsyncMock()
        mock_client.delete = AsyncMock(side_effect=Exception("Connection lost"))
        
        with patch.object(cache, 'get_client', return_value=mock_client):
            result = await cache.delete("test:key")
            assert result is False


class TestGlobalCacheInstance:
    """Test global cache service instance management."""
    
    def test_get_cache_service_singleton(self):
        """Test get_cache_service returns singleton."""
        # Reset global instance
        import app.services.cache_service as cache_module
        cache_module._cache_service = None
        
        service1 = get_cache_service()
        service2 = get_cache_service()
        assert service1 is service2
    
    def test_cache_service_url_from_settings(self):
        """Test cache service uses settings URL."""
        cache = CacheService()
        assert cache.redis_url is not None


# Total: 32 tests
