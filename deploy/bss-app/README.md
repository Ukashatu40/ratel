# deploy/bss-app

Business host (not created yet). Runs the **app** (RatelBSS, RatelMeter API, RatelDesk and RatelPay back ends) with PostgreSQL and Redis on the same VM. Public only through a reverse proxy, and only RatelPay and the payment webhook; everything else VPN-only.

Deployment is Docker Compose or systemd, per the Build Plan. **No deployment files exist yet.**
TODO: unit files or compose file, environment-file template (placeholders only), runbook in
docs/runbooks/, rollback procedure.

Rules: secrets live in owner-only environment files on the host, never here. Production changes go
through reviewed commits. Nobody edits production by hand. A bad deploy here must never be able to
take RatelCore down, which is why business, voice and ops each have their own VM.

Owner: Software team (project lead). TODO: confirm host details and deployment credentials handling.
