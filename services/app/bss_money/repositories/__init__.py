"""Storage. `ports.py` says what the services need. `sql.py` implements it on PostgreSQL.

May import: domain (and, in `sql.py` only, models). Must not import: services, FastAPI. Services
import `ports` only, never `sql`, so they can be tested with an in-memory fake. Everything here
works inside the caller's transaction and never commits.
"""
