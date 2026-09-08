#!/usr/bin/env python3
"""
Initialize the database and create all tables.
Run this first before starting the application.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.database import init_db
from backend.models.models import *  # noqa: F403

def init_database():
    print("Creating database tables (WAL mode)...")
    init_db()
    print("Database initialized successfully!")
    print(f"Database file: sqlite:///./offpage_seo.db")

if __name__ == "__main__":
    init_database()
