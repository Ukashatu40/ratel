# deploy/voice

RatelVoice host (not created yet). Runs the **meter-agent** in call mode next to Kamailio. Configuration in network/voice/.

Deployment is Docker Compose or systemd, per the Build Plan. **No deployment files exist yet.**
TODO: unit files or compose file, environment-file template (placeholders only), runbook in
docs/runbooks/, rollback procedure.

Rules: secrets live in owner-only environment files on the host, never here. Production changes go
through reviewed commits. Nobody edits production by hand. A bad deploy here must never be able to
take RatelCore down, which is why business, voice and ops each have their own VM.

Owner: Network team. TODO: confirm host details and deployment credentials handling.
