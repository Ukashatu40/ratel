"""Services: the use cases of RatelBSS: money. They combine domain rules and the repository port.

May import: domain, repositories.ports, common. Must not import: SQLAlchemy, FastAPI,
repositories.sql, models. A service takes its dependencies as arguments, so it runs against an
in-memory fake in tests and against PostgreSQL in production.
"""
