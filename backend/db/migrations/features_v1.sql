-- Migration: features_v1.sql
-- Description: Adds tables for Personal Finance, Link Bookmarking, Notification Channels, and Deep Web Crawling

CREATE TABLE IF NOT EXISTS user_portfolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_symbol TEXT UNIQUE NOT NULL,
    asset_type TEXT NOT NULL CHECK(asset_type IN ('STOCK', 'CRYPTO', 'COMMODITY', 'FOREX')),
    asset_name TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0.0,
    buy_price REAL NOT NULL DEFAULT 0.0,
    current_price REAL NOT NULL DEFAULT 0.0,
    price_change_24h REAL NOT NULL DEFAULT 0.0,
    alert_threshold_pct REAL NOT NULL DEFAULT 5.0,
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS watchlist_alerts (
    alert_id TEXT PRIMARY KEY,
    asset_symbol TEXT NOT NULL,
    trigger_condition TEXT NOT NULL CHECK(trigger_condition IN ('CHANGE_GE_5PCT', 'PRICE_ABOVE', 'PRICE_BELOW')),
    target_value REAL NOT NULL,
    last_triggered_at TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'MUTED', 'TRIGGERED')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS user_links (
    link_id TEXT PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    domain TEXT,
    summary TEXT,
    raw_content TEXT,
    tags TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'CRAWLING', 'INDEXED', 'FAILED')),
    chroma_indexed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS notification_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS web_crawl_sessions (
    session_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    current_depth INTEGER NOT NULL DEFAULT 0,
    max_depth INTEGER NOT NULL DEFAULT 3,
    status TEXT NOT NULL DEFAULT 'RUNNING' CHECK(status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    extracted_facts TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
