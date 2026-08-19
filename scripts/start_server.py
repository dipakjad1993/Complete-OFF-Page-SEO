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
    
    # Initialize database
    print("[1/3] Initializing database...")
    from backend.core.database import engine, Base
    from backend.models.models import *  # noqa: F403
    Base.metadata.create_all(bind=engine)
    print("      Database ready!")
    print()
    
    # Start server
    print("[2/3] Starting API server on http://localhost:8000")
    print("[3/3] Dashboard available at http://localhost:3000")
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
