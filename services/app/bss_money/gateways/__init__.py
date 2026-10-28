"""Payment gateways: one module per provider, each implementing `domain.payments.PaymentGateway`.

May import: `domain` and an HTTP client. Must not import: services, repositories, models, FastAPI.
"""
