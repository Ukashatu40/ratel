"""Storage. `ports.py` says what the services need. `mongo.py` implements it.

May import: domain (and config for connection settings). Must not import: api, services, security.
Services import `ports` only, never `mongo`, so they can be tested with in-memory fakes.
"""
