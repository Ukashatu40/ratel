"""A RatelDesk app on a real PostgreSQL, with staff signed in and a fake RatelLink.

Shared by the integration tests that drive the routes against the migrated database.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.bss_lines.api.lines import get_client
from app.config import Settings
from app.main import create_app
from tests.app.bss_lines.desk_helpers import PASSWORD, add_staff
from tests.app.bss_lines.fakes import FakeRatelLinkClient
from tests.app.bss_money.postgres import Database
from tests.app.bss_money.rating_data import SeededLine, seed_line


class Desk:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.network = FakeRatelLinkClient()
        self.app: FastAPI = create_app(Settings(database_url=db.url, staff_cookie_secure=False))  # type: ignore[arg-type]
        self.app.dependency_overrides[get_client] = lambda: self.network
        factory = sessionmaker(db.engine, expire_on_commit=False)
        self.agent = self._sign_in(factory, "agent")
        self.admin = self._sign_in(factory, "admin")

    def _sign_in(self, factory: sessionmaker[Session], role: str) -> TestClient:
        email = add_staff(factory, role)
        client = TestClient(self.app)
        client.headers["x-ratel-desk"] = "1"
        assert (
            client.post("/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code
            == 200
        )
        return client

    def lines(self, count: int = 1, state: str = "active") -> list[SeededLine]:
        with Session(self.db.engine) as session, session.begin():
            return [seed_line(session, n, state=state) for n in range(1, count + 1)]

    def buy(self, line: SeededLine, key: str):  # type: ignore[no-untyped-def]
        return self.agent.post(
            f"/v1/lines/{line.line_id}/purchases",
            json={"offer_kind": "plan", "offer_id": line.plan_id},
            headers={"Idempotency-Key": key},
        )

    def activate(self, line: SeededLine, key: str):  # type: ignore[no-untyped-def]
        return self.agent.post(
            f"/v1/lines/{line.line_id}/activate", json={}, headers={"Idempotency-Key": key}
        )
