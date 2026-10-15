# deploy/core-cp

The RatelCore control-plane host. It runs RatelCore itself (the network team's, not in this
repository) and **RatelLink**. This folder holds everything needed to install RatelLink there.

**Status: verified in a clean Linux container, not yet on core-cp.** The files below were run end
to end in a throwaway Linux container with an unprivileged service user and the least-privilege
MongoDB user (install, start with the unit's own `ExecStart`, the whole API flow, upgrade,
rollback, a loosened key file). Nobody has followed this on core-cp yet. The first real install is
the first real test, and any difference found there should be fixed in these files.

Rules: secrets live in owner-only files on the host, never here. Production changes go through
reviewed commits. Nobody edits production by hand. A bad deploy here must never be able to take
RatelCore down, which is why business, voice and ops each have their own VM.

## What is here

| File | Purpose |
| ---- | ------- |
| `mongo/ratel-link-roles.json` | The MongoDB privileges RatelLink needs, and nothing more |
| `mongo/create-ratel-link-user.js` | Applies them: creates the roles and the `ratel_link` user (`mongosh`) |
| `ratel-link.env.example` | The settings file, with placeholders |
| `ratel-link.service` | The systemd unit (hardened, listens on 127.0.0.1 only) |
| `install-release.sh` | Installs a release into its own folder and switches `current` to it |
| `nginx/ratel-link.conf.example` | A TLS proxy template for callers on other hosts |

## Layout on core-cp

```
/opt/ratel-link/releases/<release>/   code and its own virtualenv (owned by root, read-only)
/opt/ratel-link/current               a link to the active release
/etc/ratel-link/ratel-link.env        settings and the MongoDB password (service user, mode 0600)
/etc/ratel-link/ratel_link.key        the encryption key for Ki and OPc (service user, mode 0600)
```

## Before the first install (the network team)

These are not developer tasks and nothing goes near real SIMs until they are done (Build Plan).

1. **MongoDB authentication is on**, MongoDB is bound to `127.0.0.1`, and the HSS and PCRF
   configurations are updated to match.
2. The core's `subscribers` collection has a **unique index on `imsi`**. RatelLink never creates
   indexes in the core's database. It checks, and logs `startup.subscribers.index.missing` if the
   index is not there.
3. **Create RatelLink's database user.** From this folder, with an administrator account:

   ```
   cd deploy/core-cp/mongo
   RATEL_LINK_DB_PASSWORD="$(openssl rand -base64 33 | tr -d '/+=')" \
     mongosh "<administrator connection string>" --file create-ratel-link-user.js
   ```

   The password is generated and read from the environment, so it is never typed or put in a
   command line. Take it from the shell into `ratel-link.env` without displaying it. Run the
   script again at any time to change the password or to apply an updated `ratel-link-roles.json`.

   What the user can do: read and write RatelLink's own collections, but **never change or delete a
   stored SIM key, never read, change or delete an audit entry** (insert only), and never delete
   anything of its own. In the core's database it can read, insert, update and **delete**
   `subscribers` (deactivating a line deletes its document) and nothing else: no index, no other
   collection. `tests/ratel_link/repositories/test_mongo_roles_integration.py`
   proves both halves against a real MongoDB: RatelLink does all its work with exactly these
   privileges, and every operation outside them is refused.
4. **Agree with RatelLink's owner** the address range for lines (`RATEL_LINK_UE_POOL`, outside the
   SMF's dynamic range) and supply the voice template (`RATEL_LINK_VOICE_TEMPLATE_FILE`). See
   [docs/RATELCORE_INTEGRATION_FACTS.md](../../docs/RATELCORE_INTEGRATION_FACTS.md), N1 and N2.

## First install

On a developer machine, from a reviewed commit on `main`:

```
git archive --format=tar.gz --prefix=ratel-link-$(git rev-parse --short HEAD)/ \
  -o ratel-link-$(git rev-parse --short HEAD).tar.gz HEAD services/ratel_link services/common requirements
```

Copy the tarball and `install-release.sh` to core-cp (by the usual secure copy, not by chat or
email). Then, on core-cp:

```
sudo ./install-release.sh ratel-link-<commit>.tar.gz python3.12   # Python 3.12 or newer
sudo cp ratel-link.env.example /etc/ratel-link/ratel-link.env      # then edit it, see below
sudo chown ratellink:ratellink /etc/ratel-link/ratel-link.env && sudo chmod 600 /etc/ratel-link/ratel-link.env
sudo cp ratel-link.service /etc/systemd/system/ && sudo systemctl daemon-reload
```

The install needs the Python package index (PyPI) reachable from core-cp. If it is not, build the
release's packages on another machine (`pip download -r requirements/link.txt -c requirements/constraints.txt -d wheels`)
and install with `pip install --no-index --find-links wheels`. TODO(network team): say which it is.

Edit `/etc/ratel-link/ratel-link.env`: put the generated MongoDB password into `MONGO_URI`, and set
`RATEL_LINK_UE_POOL` once the range is agreed. Then, as the service user (the settings are loaded
the same way the unit loads them):

```
RUN="sudo -u ratellink env PYTHONPATH=/opt/ratel-link/current/services bash -c 'set -a; . /etc/ratel-link/ratel-link.env; set +a; exec \"\$@\"' _"
$RUN /opt/ratel-link/current/venv/bin/python -m ratel_link.admin_cli key generate --out /etc/ratel-link/ratel_link.key
$RUN /opt/ratel-link/current/venv/bin/python -m ratel_link.admin_cli init-db
$RUN /opt/ratel-link/current/venv/bin/python -m ratel_link.admin_cli api-key create --id bss-app --name RatelBSS
```

- **Back up the key file offline, and never with the database backups, before importing any real
  SIM.** Losing it loses every stored Ki and OPc. Owner and procedure: see the runbook.
- `api-key create` prints the key **once**. Put it straight into the caller's owner-only file.
- Never pass the key or a password through a ticket, chat or email.

Start it:

```
sudo systemctl enable --now ratel-link
journalctl -u ratel-link -n 50 --no-pager
curl -s http://127.0.0.1:8081/healthz
```

A healthy start shows no `ERROR` line. Expected warnings until the network team's inputs arrive:
`startup.voice.template.not_configured`.

## Reaching it from other hosts

RatelLink listens on `127.0.0.1` only. RatelBSS (on bss-app) and the RatelMeter agent (on core-up)
reach it through a TLS proxy on core-cp that allows only their addresses and limits the request
rate (the project lead's decision of 2026-10-10, until the VPN exists). `nginx/ratel-link.conf.example`
is a template with those four properties. Its access log records who called and the result, **never
the path**, because paths contain IMSIs. Replace every `<placeholder>`, test with `nginx -t`, and
do not open the port to anything else.

## Upgrade

```
sudo ./install-release.sh ratel-link-<new-commit>.tar.gz python3.12   # nothing restarts yet
sudo systemctl restart ratel-link
journalctl -u ratel-link -n 50 --no-pager && curl -s http://127.0.0.1:8081/healthz
```

The new release is installed beside the old one. If the install fails, it is removed and the
active release is not touched.

## Rollback

Old releases are kept. To go back, point `current` at the previous release and restart:

```
ls /opt/ratel-link/releases
sudo ln -sfn /opt/ratel-link/releases/<previous> /opt/ratel-link/current.new && sudo mv -Tf /opt/ratel-link/current.new /opt/ratel-link/current
sudo systemctl restart ratel-link
```

A code rollback changes no stored data. Stored Ki and OPc are encrypted: **an older release that
predates the encryption code cannot read them** (ADR 0006), so never roll back past it.

Owner: the RatelLink owner, with the network team. TODO: confirm host details and how deployment
credentials are handled.
