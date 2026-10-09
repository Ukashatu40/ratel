"""Services: the use cases. They combine domain rules, security primitives and storage ports.

This is RatelLink's business logic layer (not the top-level `services/` folder of the repository).
May import: domain, security, repositories.ports, config, common. Must not import: api,
repositories.mongo, FastAPI or pymongo. A service takes its dependencies as arguments.
"""
