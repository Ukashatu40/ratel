# deploy/bss-app

Business host. Runs the **app** (RatelBSS, the RatelMeter API, and the RatelDesk and RatelPay back ends)
with PostgreSQL and Redis on the same VM. Public only through a reverse proxy, and only RatelPay and the
payment webhook; everything else is for the office network and the VPN.

**Status (2026-10-23): drafted, never run on a real host.** The VM does not exist yet (the network lead was
asked to create it). What was proven without it: the install script and the dependencies in a clean Ubuntu-like
container with **no network**, the app starting as the service user and answering `/healthz`, the unit with
`systemd-analyze verify` on Ubuntu 24.04's systemd, and the two PostgreSQL roles on a throwaway database
(migrations as the owner, then the service role can read and write rows and cannot change the schema). **Not
proven:** everything on the real host (PostgreSQL and Redis from apt, the proxy and its certificate, boot,
restart on failure, backups). Write down every difference from these steps in the PR that fixes the files.

Rules: secrets live in owner-only environment files on the host, never here. Production changes go through
reviewed commits. Nobody edits production by hand. A bad deploy here must never be able to take RatelCore
down, which is why business, voice and ops each have their own VM.

Owner: Software team (project lead). TODO: confirm host details and how deployment credentials are handled.

## What is here

| File | Purpose |
| ---- | ------- |
| `install-release.sh` | Installs a release into its own folder with its own virtualenv and points `current` at it. Never restarts anything and never runs a migration |
| `ratel-app.service` | The app. Runs as the unprivileged user `ratelbss`, no capabilities, listens on `127.0.0.1:8000` |
| `ratel-app.env.example` | The app's settings, with placeholders |
| `ratel-rating.service`, `.timer` | The rating job every five minutes (usage, out of data, restore, and renewal if turned on) |
| `ratel-ledger-check.service`, `.timer` | The nightly check that every wallet equals its ledger |
| `postgres-roles.sql` | The two database roles: an owner for migrations, and a runtime role that cannot change the schema |
| `nginx/ratel-app.conf.example` | A TLS reverse proxy template. The one public path so far is the voucher redemption; the RatelPay page and the webhook are TODO until they exist |
| `nginx/ratel-pay-key.conf.example` | The one line that adds the redemption key (`PAY_API_KEY`) to that public path. Real file: root-owned, never committed |

## Layout on bss-app

```
/opt/ratel-app/releases/<release>/   code and its own virtualenv (owned by root, read-only)
/opt/ratel-app/current               a link to the active release (the unit runs from here)
/etc/ratel-app/ratel-app.env         the app's settings, database password and API keys (mode 0600)
/etc/ratel-app/ratel-app-migrate.env DATABASE_URL of the owner role, for migrations only (root, mode 0600)
```

## Installation

Assumes **Ubuntu 24.04 LTS**, which ships Python 3.12 (so none of the source-build work the 22.04 core hosts
needed), PostgreSQL 16 (the version CI tests against) and Redis 7. On another OS, change step 1.

1. **Host packages, and check the services listen on this host only:**
   ```bash
   sudo apt-get install -y python3.12 python3.12-venv postgresql redis-server nginx chrony
   sudo ss -tlnp | grep -E ':(5432|6379)\b'     # both must show 127.0.0.1, never 0.0.0.0
   chronyc tracking | grep -E 'Leap status|System time'
   ```

2. **Create the database and its two roles, then set their passwords at the prompt** (never in a file or on
   a command line):
   ```bash
   sudo -u postgres psql -v ON_ERROR_STOP=1 -f postgres-roles.sql
   sudo -u postgres psql -c '\password ratel_owner'
   sudo -u postgres psql -c '\password ratel_app'
   ```

3. **Build the release on your machine, from a reviewed commit on `main`**, with its dependencies inside
   (about 27 wheels, so installing needs no internet on bss-app), and copy it over:
   ```bash
   git switch main && git pull
   scripts/release/build-release.sh app HEAD /tmp          # prints the tarball name and its SHA-256
   REL=ratel-app-$(git rev-parse --short HEAD)
   scp /tmp/$REL.tar.gz deploy/bss-app/install-release.sh deploy/bss-app/ratel-app.service \
     deploy/bss-app/ratel-rating.service deploy/bss-app/ratel-rating.timer \
     deploy/bss-app/ratel-ledger-check.service deploy/bss-app/ratel-ledger-check.timer \
     deploy/bss-app/ratel-app.env.example deploy/bss-app/nginx/ratel-app.conf.example \
     deploy/bss-app/nginx/ratel-pay-key.conf.example <bss-app>:/tmp/
   ```
   On bss-app, compare `sha256sum /tmp/$REL.tar.gz` with the value printed above.

4. **Install the release** (creates the user `ratelbss` and the folders, checks the service user can import it):
   ```bash
   cd /tmp && sudo ./install-release.sh $REL.tar.gz python3.12
   ```
   If it fails, the half-made release is removed and nothing else changes.

5. **Install the settings.** Put the passwords and keys in without displaying them in a ticket or chat:
   ```bash
   sudo install -m 0600 -o ratelbss -g ratelbss /tmp/ratel-app.env.example /etc/ratel-app/ratel-app.env
   sudo -e /etc/ratel-app/ratel-app.env
   sudo install -m 0600 -o root -g root /dev/null /etc/ratel-app/ratel-app-migrate.env
   sudo -e /etc/ratel-app/ratel-app-migrate.env      # one line: DATABASE_URL=postgresql+psycopg://ratel_owner:<password>@127.0.0.1:5432/ratel_bss
   ```

6. **Run the database migrations as the owner role** (a deliberate step, never part of an install). Read the
   migration first: some refuse to roll back while they hold rows.
   ```bash
   sudo systemd-run --wait --pipe -p User=ratelbss -p EnvironmentFile=/etc/ratel-app/ratel-app-migrate.env \
     -p Environment=PYTHONPATH=/opt/ratel-app/current/services -p Environment=PYTHONDONTWRITEBYTECODE=1 \
     /opt/ratel-app/current/venv/bin/python -m alembic -c /opt/ratel-app/current/services/app/alembic.ini upgrade head
   ```

7. **Install the unit, check it with the host's own systemd, and start it:**
   ```bash
   sudo cp /tmp/ratel-app.service /etc/systemd/system/ && sudo systemctl daemon-reload
   sudo systemd-analyze verify /etc/systemd/system/ratel-app.service     # must print nothing about this file
   sudo systemctl start ratel-app.service
   curl -s http://127.0.0.1:8000/healthz                                 # {"status":"ok"}
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/readyz   # 200 once migrations ran and Redis answers
   ```
   A 503 from `/readyz` names its reason only in the journal (`readiness.failed`: `database`, `migrations`,
   `redis` or `ratel_link_key`). Enable it at boot (`systemctl enable`) only when you are happy, then reboot once to prove it comes back.

8. **The proxy.** Copy `ratel-app.conf.example` to `/etc/nginx/conf.d/ratel-app.conf`, replace every
   `<placeholder>`, install the certificate, then make the redemption key: `openssl rand -base64 32`, put it in
   `/etc/ratel-app/ratel-app.env` as `PAY_API_KEY` and, from `ratel-pay-key.conf.example`, in
   `/etc/nginx/ratel-pay-key.conf` (root-owned, group of the nginx user, mode 0640; the same value in both).
   Test with `sudo nginx -t`, then reload. TODO: the domain name and
   certificate for RatelPay, and the firewall rules (443 public for RatelPay and the webhook only; 22 from admin
   addresses only; the core-up and voice agents to the usage path only).

9. **The timers** (after the app answers `healthz` and the migrations are done). Copy the four files, check them, and
   enable the timers (not the services, which the timers start):
   ```bash
   sudo cp /tmp/ratel-rating.service /tmp/ratel-rating.timer /tmp/ratel-ledger-check.service \
     /tmp/ratel-ledger-check.timer /etc/systemd/system/ && sudo systemctl daemon-reload
   sudo systemd-analyze verify /etc/systemd/system/ratel-rating.{service,timer} /etc/systemd/system/ratel-ledger-check.{service,timer}
   sudo systemctl enable --now ratel-rating.timer ratel-ledger-check.timer
   systemctl list-timers 'ratel-*'
   sudo systemctl start ratel-rating.service; systemctl status ratel-rating.service --no-pager | head -8
   ```
   The rating job needs `RATEL_LINK_API_KEY` set to a real key in `ratel-app.env` (it exits 2 without one). Decide
   `RATING_AUTO_RENEW` and `VAT_RATE_BPS` there too (docs/runbooks/bss-app.md says what each does). A timer that
   missed its time while the host was off runs once as soon as the host is back (the nightly power cut).

10. **The first admin** (after the migrations). RatelDesk's staff sign in with an email and a password; there is no
    sign-up and no default account. Make the first admin by hand, typing the password at the prompt (it is never an
    argument), then check you can sign in through the proxy. More accounts and the day-to-day tasks are in
    docs/runbooks/bss-app.md, "Staff accounts":
    ```bash
    sudo -u ratelbss env PYTHONPATH=/opt/ratel-app/current/services \
      bash -c 'set -a; . /etc/ratel-app/ratel-app.env; set +a; exec "$@"' _ \
      /opt/ratel-app/current/venv/bin/python -m app.bss_lines.staff_cli create --email <you> --name "<your name>" --role admin
    ```

## Upgrade and rollback

Upgrade: build a new release (step 3), install it (step 4), run the migrations if the release has new ones
(step 6), then `sudo systemctl restart ratel-app.service`. Rollback: point `/opt/ratel-app/current` at the
previous release in `/opt/ratel-app/releases/` (`sudo ln -sfn <old release> /opt/ratel-app/current`) and restart.
Old releases are never deleted by the script. A code rollback changes no data. **A migration is not undone by
pointing at an old release:** `alembic downgrade -1` refuses to drop tables that hold rows, so restore from a
backup instead.

## Verification

```bash
sudo systemctl status ratel-app.service
sudo journalctl -u ratel-app.service -n 50 --no-pager
curl -s http://127.0.0.1:8000/healthz
```
`journalctl` must show no `ERROR` line. See [docs/runbooks/bss-app.md](../../docs/runbooks/bss-app.md) for diagnostics.
