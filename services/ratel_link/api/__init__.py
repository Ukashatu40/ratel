"""HTTP layer: routes, request and response bodies, authentication dependency.

May import: services, domain, FastAPI, common. Must not import: repositories or security
directly. Routes stay thin: validate, call a service, shape the response. Add every Contract 1 route
to `router.new_v1_router()` so it requires an API key by default (docs/adr/0007).
"""
