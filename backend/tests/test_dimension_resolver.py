"""Tests for DimensionResolver — cache hit consistency and invalidation path."""

import asyncio
import pytest
import sys
import os
import sqlite3

# Ensure backend/ is on path when running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.dimension_resolver import DimensionResolver, _normalize_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def ensure_table():
    """Create the dimension_decisions table in knowledge.sqlite before each test."""
    from db.connections import get_knowledge_db
    from pathlib import Path
    migration = Path(__file__).parent.parent / "db" / "migrations" / "dimension_decisions_v1.sql"
    conn = get_knowledge_db()
    try:
        conn.executescript(migration.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_resolver() -> DimensionResolver:
    return DimensionResolver(web_search_fn=None)


# ---------------------------------------------------------------------------
# Test 1: Same object built twice → second run is a cache hit with same value
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_consistency():
    resolver = _fresh_resolver()
    category = "test_lamp_cache"
    descriptor = "modern"
    dimension = "height_cm"
    model_value = 45.0
    model_confidence = 0.85

    # First resolve — cache miss, stores value
    result1 = await resolver.resolve(
        task_id="task_test_001",
        category=category,
        descriptor=descriptor,
        dimension_name=dimension,
        model_value=model_value,
        model_confidence=model_confidence,
    )
    assert result1.from_cache is False
    assert result1.value == model_value
    assert result1.source == "prior_knowledge"

    # Second resolve — must be a cache hit with identical value
    result2 = await resolver.resolve(
        task_id="task_test_002",
        category=category,
        descriptor=descriptor,
        dimension_name=dimension,
        model_value=99.0,   # different model guess — should be ignored
        model_confidence=0.9,
    )
    assert result2.from_cache is True, "Second resolve must return from_cache=True"
    assert result2.value == model_value, (
        f"Cached value {result2.value} must match first stored value {model_value}"
    )


# ---------------------------------------------------------------------------
# Test 2: Invalidate → third run re-derives (from_cache=False)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalidation_forces_rederive():
    resolver = _fresh_resolver()
    category = "test_lamp_invalidate"
    descriptor = ""
    dimension = "base_radius_cm"
    model_value = 12.0
    model_confidence = 0.75

    key = _normalize_key(category, descriptor, dimension)

    # First resolve — stores value
    result1 = await resolver.resolve(
        task_id="task_inv_001",
        category=category,
        descriptor=descriptor,
        dimension_name=dimension,
        model_value=model_value,
        model_confidence=model_confidence,
    )
    assert result1.from_cache is False

    # Second resolve — cache hit
    result2 = await resolver.resolve(
        task_id="task_inv_002",
        category=category,
        descriptor=descriptor,
        dimension_name=dimension,
        model_value=model_value,
        model_confidence=model_confidence,
    )
    assert result2.from_cache is True

    # Simulate assembly verification failure → invalidate
    resolver.invalidate(key, reason="penetration/overlap: base_radius too large")

    # Confirm _get_active returns None (entry is now SUSPECT, not ACTIVE)
    active = resolver._get_active(key)
    assert active is None, "After invalidation, _get_active must return None"

    # Third resolve — must re-derive (from_cache=False) with new model value
    new_model_value = 10.0
    result3 = await resolver.resolve(
        task_id="task_inv_003",
        category=category,
        descriptor=descriptor,
        dimension_name=dimension,
        model_value=new_model_value,
        model_confidence=0.8,
    )
    assert result3.from_cache is False, "After invalidation, resolve must re-derive"
    assert result3.value == new_model_value
