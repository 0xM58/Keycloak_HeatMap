#!/usr/bin/env python3

import json
import os
import time
from datetime import datetime

import dotenv
import httpx
import sqlalchemy
from google.cloud.sql.connector import Connector

from database import (
    get_ips_without_geolocation,
    init_database,
    update_geolocation,
    upsert_ip_data,
)

dotenv.load_dotenv()

DB_INSTANCE_CONNECTION_NAME = os.getenv("DB_INSTANCE_CONNECTION_NAME")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SCHEMA = os.getenv("DB_SCHEMA")
KC_REALM_ID = os.getenv("KC_REALM_ID")
COLLECTION_INTERVAL = int(os.getenv("COLLECTION_INTERVAL", "3600"))


def connect_to_database() -> sqlalchemy.engine.base.Connection:
    """Connect to Google Cloud SQL"""
    connector = Connector()

    def getconn():
        return connector.connect(
            DB_INSTANCE_CONNECTION_NAME,
            "pg8000",
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
        )

    engine = sqlalchemy.create_engine("postgresql+pg8000://", creator=getconn)
    connection = engine.connect()
    connection.execute(sqlalchemy.text(f"SET search_path TO '{DB_SCHEMA}'"))
    return connection


def extract_ip(data_json: str) -> str | None:
    """Extract IP from session data"""
    try:
        data = json.loads(data_json)
        return data.get("ipAddress")
    except json.JSONDecodeError:
        return None


def collect_ip_data():
    """Collect IP data from Keycloak sessions and update database"""
    print(f"[{datetime.now()}] Starting IP data collection...")

    try:
        conn = connect_to_database()
        result = conn.execute(
            sqlalchemy.text("""
                SELECT u.email, s.data
                FROM offline_user_session s
                JOIN user_entity u ON s.user_id = u.id
                WHERE s.realm_id = :realm_id
            """),
            {"realm_id": KC_REALM_ID},
        )
        sessions = result.fetchall()
        conn.close()

        # Group by IP
        ip_to_users = {}
        for email, data in sessions:
            ip = extract_ip(data)
            if ip:
                if ip not in ip_to_users:
                    ip_to_users[ip] = []
                ip_to_users[ip].append(email)

        # Filter shared IPs (more than 1 user, and not duplicate emails)
        shared_ips = {
            ip: emails
            for ip, emails in ip_to_users.items()
            if len(emails) > 1 and len(set(emails)) > 1
        }

        # Update database
        for ip, emails in shared_ips.items():
            upsert_ip_data(ip, len(emails), emails)

        print(f"[{datetime.now()}] Collection complete: {len(shared_ips)} shared IPs")

    except Exception as e:
        print(f"[{datetime.now()}] Error collecting IP data: {e}")


def fetch_geolocation(ip: str) -> tuple[float | None, float | None]:
    """Fetch geolocation using keycdn-tools API"""
    try:
        response = httpx.get(
            f"ipinfo.io/{ip}/json",
            timeout=10.0,
        )
        data = response.json()
        if "loc" in data:
            lat, lon = data["loc"].split(",")
            return float(lat), float(lon)
        else:
            return None, None

    except Exception as e:
        print(f"Error fetching geolocation for {ip}: {e}")
        return None, None


def process_pending_geolocations():
    """Process IPs that don't have geolocation data yet (1 request per second)"""
    pending_ips = get_ips_without_geolocation()

    if not pending_ips:
        print(f"[{datetime.now()}] No pending geolocations")
        return

    print(f"[{datetime.now()}] Processing {len(pending_ips)} pending geolocations...")

    for i, ip in enumerate(pending_ips, start=1):
        print(f"[{datetime.now()}] Fetching {ip} ({i}/{len(pending_ips)})")

        lat, lon = fetch_geolocation(ip)

        if lat and lon:
            update_geolocation(ip, lat, lon)
            print(f"[{datetime.now()}] ✓ {ip} -> ({lat}, {lon})")
        else:
            print(f"[{datetime.now()}] ✗ {ip} -> Failed")

        if i < len(pending_ips):
            time.sleep(1.0)

    print(f"[{datetime.now()}] Geolocation processing complete")


def run_scheduler():
    """Main scheduler loop: collect IPs every hour, process geolocations continuously"""
    init_database()
    print(f"[{datetime.now()}] Scheduler started")

    # Initial collection
    collect_ip_data()
    process_pending_geolocations()

    last_collection = time.time()

    while True:
        current_time = time.time()

        if current_time - last_collection >= COLLECTION_INTERVAL:
            collect_ip_data()
            last_collection = current_time

        process_pending_geolocations()

        time.sleep(60)


if __name__ == "__main__":
    run_scheduler()
