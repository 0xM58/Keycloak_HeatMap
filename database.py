#!/usr/bin/env python3

import os
import dotenv
import sqlite3
from datetime import datetime
from typing import Optional

dotenv.load_dotenv()

DB_PATH = os.getenv("DB_LOCAL_PATH", "ip_locations.db")


def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table for IP information
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ip_data (
            ip TEXT PRIMARY KEY,
            user_count INTEGER NOT NULL,
            emails TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            geolocation_fetched INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def upsert_ip_data(ip: str, user_count: int, emails: list[str]):
    """Insert or update IP data (without changing geolocation if already set)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    emails_str = ", ".join(sorted(emails))

    cursor.execute(
        """
        INSERT INTO ip_data (ip, user_count, emails, last_updated)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(ip) DO UPDATE SET
            user_count = excluded.user_count,
            emails = excluded.emails,
            last_updated = excluded.last_updated
    """,
        (ip, user_count, emails_str, datetime.now()),
    )

    conn.commit()
    conn.close()


def update_geolocation(ip: str, latitude: float, longitude: float):
    """Update geolocation data for an IP"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE ip_data
        SET latitude = ?, longitude = ?, geolocation_fetched = 1
        WHERE ip = ?
    """,
        (latitude, longitude, ip),
    )

    conn.commit()
    conn.close()


def get_ips_without_geolocation() -> list[str]:
    """Get list of IPs that don't have geolocation data yet"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ip FROM ip_data
        WHERE geolocation_fetched = 0 OR latitude IS NULL OR longitude IS NULL
    """)

    ips = [row[0] for row in cursor.fetchall()]
    conn.close()
    return ips


def get_all_ip_data() -> list[dict]:
    """Get all IP data with geolocation"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ip, user_count, emails, latitude, longitude, last_updated
        FROM ip_data
        WHERE geolocation_fetched = 1 AND latitude IS NOT NULL AND longitude IS NOT NULL
        ORDER BY user_count DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "ip": row[0],
            "user_count": row[1],
            "emails": row[2],
            "latitude": row[3],
            "longitude": row[4],
            "last_updated": row[5],
        }
        for row in rows
    ]


def get_stats() -> dict:
    """Get database statistics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM ip_data")
    total_ips = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM ip_data WHERE geolocation_fetched = 1")
    located_ips = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(user_count) FROM ip_data")
    total_users = cursor.fetchone()[0] or 0

    conn.close()

    return {
        "total_ips": total_ips,
        "located_ips": located_ips,
        "pending_ips": total_ips - located_ips,
        "total_users": total_users,
    }
