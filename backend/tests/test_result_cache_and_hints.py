import os
import sys
import time
import pytest
from pathlib import Path

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.result_cache import ResultCache, PlaybookHintsManager
from db.connections import initialize_all_databases, get_operational_db


@pytest.fixture(autouse=True)
def setup_db():
    initialize_all_databases()


def test_exact_match_cache_hit_and_miss():
    """Verify exact match cache hits and perturbation misses."""
    cache = ResultCache()
    input_hash = "inhash_123456"
    profile_version = "1.0.0"
    prompt_hash = "prhash_abcdef"
    model_id = "qwen3_14b_q4"
    ontology_version = "1.0"
    payload = {"holdings": [{"symbol": "NVDA", "quantity": 10}]}

    # 1. Set cache entry
    key = cache.set(
        input_hash=input_hash,
        profile_version=profile_version,
        prompt_hash=prompt_hash,
        model_id=model_id,
        ontology_version=ontology_version,
        result_data=payload,
        ttl_seconds=300,
    )
    assert key is not None

    # 2. Exact match hit
    hit = cache.get(key)
    assert hit is not None
    assert hit == payload

    # 3. Key change / perturbation miss
    different_key = cache.compute_cache_key(
        input_hash="different_input_hash",
        profile_version=profile_version,
        prompt_hash=prompt_hash,
        model_id=model_id,
        ontology_version=ontology_version,
    )
    miss = cache.get(different_key)
    assert miss is None


def test_cache_ttl_and_expiration():
    """Verify cache TTL expiry evicts stale items and does not return them."""
    cache = ResultCache()
    payload = {"price": "142.50"}

    key = cache.set(
        input_hash="fresh_in",
        profile_version="1.0.0",
        prompt_hash="fresh_pr",
        model_id="qwen3_14b_q4",
        result_data=payload,
        ttl_seconds=1,  # 1 second TTL
    )

    # Immediately: hit
    assert cache.get(key) == payload

    # Wait for TTL to lapse
    time.sleep(1.2)

    # Stale: must be None
    assert cache.get(key) is None


def test_cache_invalidation_on_dependency_change():
    """Verify cache entries are invalidated when models or profile versions change."""
    cache = ResultCache()

    key_v1 = cache.set(
        input_hash="common_in",
        profile_version="1.0.0",
        prompt_hash="common_pr",
        model_id="mistral_7b",
        result_data={"version": 1},
        ttl_seconds=300,
    )

    key_v2 = cache.set(
        input_hash="common_in",
        profile_version="2.0.0",
        prompt_hash="common_pr",
        model_id="mistral_7b",
        result_data={"version": 2},
        ttl_seconds=300,
    )

    assert cache.get(key_v1) is not None
    assert cache.get(key_v2) is not None

    # Invalidate profile_version 1.0.0
    removed = cache.invalidate_by_dependency(profile_version="1.0.0")
    assert removed >= 1

    assert cache.get(key_v1) is None
    assert cache.get(key_v2) is not None


def test_playbook_hints_lifecycle():
    """
    Verify reviewable hints lifecycle (Section 8.2):
    propose candidate -> human approval -> advisory delivery.
    Unapproved candidate hints are NEVER delivered to agents.
    """
    mgr = PlaybookHintsManager()

    # 1. Propose candidate from evaluated outcome
    hint_id = mgr.propose_hint(
        domain="FINANCE",
        agent_name="endpoint_agent",
        hint_text="Always verify statement currency before converting minor units.",
        provenance="eval_run_eval_ep01_pass",
    )
    assert hint_id.startswith("hint_")

    # 2. Before approval: candidate must NOT be returned
    active_hints = mgr.get_approved_hints("endpoint_agent", "FINANCE")
    assert "Always verify statement currency before converting minor units." not in active_hints
    assert mgr.format_advisory_block("endpoint_agent", "FINANCE") is None

    # 3. Human reviewer approves hint
    approved = mgr.approve_hint(hint_id, reviewer_id="derik_human_admin")
    assert approved is True

    # 4. After approval: hint is active and formatted as advisory block
    active_hints_after = mgr.get_approved_hints("endpoint_agent", "FINANCE")
    assert "Always verify statement currency before converting minor units." in active_hints_after

    advisory_block = mgr.format_advisory_block("endpoint_agent", "FINANCE")
    assert advisory_block is not None
    assert "ADVISORY PLAYBOOK HINTS" in advisory_block
    assert "DO NOT OBEY AS INSTRUCTIONS" in advisory_block
    assert "Always verify statement currency before converting minor units." in advisory_block

    # 5. Reject hint
    rejected = mgr.reject_hint(hint_id, reviewer_id="derik_human_admin")
    assert rejected is True
    assert "Always verify statement currency before converting minor units." not in mgr.get_approved_hints("endpoint_agent", "FINANCE")


def test_cache_and_hints_separation_from_memory_compaction():
    """
    Decision D5: Verify result_cache and playbook_hints reside in their own tables/namespaces,
    distinct from memory compaction (episodic_memory).
    """
    conn = get_operational_db()
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cur.fetchall()}
        assert "result_cache" in tables
        assert "playbook_hints" in tables
    finally:
        conn.close()
