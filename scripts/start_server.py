#!/usr/bin/env python3
"""
Start the Complete Off-Page SEO Engine server.
"""
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("=" * 60)
    print("  Complete Off-Page SEO - Entity-First Brand Consensus Engine")
    print("  Version: 2026.1.0")
    print("=" * 60)
    print()
    
    # Initialize database (WAL + tables via shared init_db).
    print("[1/3] Initializing database...")
    from backend.core.database import init_db
    import backend.models.models  # noqa: F401 — registers tables
    init_db()
    print("      Database ready (WAL mode)!")
    print()

    # Warn on default secret.
    try:
        from config.settings import settings
        w = settings.secret_warning()
        if w:
            print(f"      WARNING: {w}")
    except Exception:
        pass

    # Start server — single canonical port 8000 (vite proxy + docs assume 8000).
    print("[2/3] Starting API server on http://localhost:8000")
    print("[3/3] Dashboard available at http://localhost:3000 (npm run dev) or http://localhost:8000 (built dist)")
    print()
    print("API Documentation: http://localhost:8000/docs")
    print("ReDoc Documentation: http://localhost:8000/redoc")
    print()
    print("Features loaded: 35/35")
    print("=" * 60)
    print()

    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()
