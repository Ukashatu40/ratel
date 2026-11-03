# deploy/voice

RatelMeter's **call agent** on the voice VM (M-10): it reads the S-CSCF's accounting (`acc` and
`missed_calls`, set up in [network/voice/scscf-acc/](../../network/voice/scscf-acc/)), joins the rows of each
call into one record, and posts finished calls to bss-app (`POST /v1/calls`). The rules it applies are in
[docs/call-record-agreement.md](../../docs/call-record-agreement.md), section 11. Call records are personal
data: nothing here logs a number or a Call-ID.

| File | What |
| ---- | ---- |
| `ratel-call-export.sh` | Prints the new rows (tab-separated). Installed as `/usr/local/sbin/ratel-call-export`, run as root through one sudo rule. Takes three whole numbers and nothing else |
| `sudoers-ratel-meter.example` | The one sudo rule: the agent's user may run that script as root, nothing more |
| `ratel-meter-calls.service` | The agent as a systemd service (user `ratelmeter`) |
| `ratel-meter-calls.env.example` | Its settings, with placeholders |

## What it does

Every 60 seconds: it delivers anything it could not deliver before (oldest first), asks the export for rows newer
than the last it read and at least 10 seconds old, and joins them per Call-ID:

- **Answered** (an `acc` INVITE 200): kept open until its first hang-up, then posted as `completed` with the
  ring and talk times. **No hang-up** after six hours (`CALL_OPEN_MAX_SECONDS`): dropped and counted in the
  journal (`meter.calls.open_calls_dropped`), never posted with an invented end.
- **Not answered** (only `missed_calls` rows): posted with the reason taken from the SIP codes of its rows:
  487 `cancelled`, 603 `declined`, 486 or 600 `not_answered`, 408, 500, 404 or 480 `unavailable`, anything else
  `failed`. (PRD decision 8 may change these; they are one function.)
- Numbers: `0XXXXXXXXXX` and `+234XXXXXXXXXX` become `234XXXXXXXXXX`. A number that matches nothing is sent as it came.
- A restart loses nothing: how far it has read and the open calls are in a state file, and finished calls wait in
  the spool until the API acknowledges them. Posting a call twice is harmless (one row per Call-ID).

## Install (the network team's VM: change nothing else on it)

1. **Python 3.12 at `/opt/python-3.12/bin/python3.12`** (Ubuntu 22.04 ships 3.10; the release's wheels are for 3.12). It sits
   next to the system Python and does not touch it, the same as on core-up: build it with
   [docs/runbooks/python-3.12-on-ubuntu-22.04.md](../../docs/runbooks/python-3.12-on-ubuntu-22.04.md) (that needs build
   packages, a package change on a core host: **ask the network lead first**). The voice VM and core-up are both
   Ubuntu 22.04 on x86_64, so copying core-up's `/opt/python-3.12` is an alternative: TODO(network lead) decide which,
   then check `/opt/python-3.12/bin/python3.12 --version`.
2. **The release.** On your machine, from a commit on `main`: `scripts/release/build-release.sh meter HEAD ~/ratel-releases`
   (the agent is one package; call mode is a flag). Copy the tarball and `deploy/core-up/install-release.sh` to the VM,
   check the SHA-256, then `sudo ./install-release.sh ratel-meter-<commit>.tar.gz /opt/python-3.12/bin/python3.12`. It creates the user
   `ratelmeter` and installs under `/opt/ratel-meter` (the same layout as core-up; the VMs are different hosts).
3. **The export script and the sudo rule:**
   ```bash
   sudo install -m 0755 -o root -g root ratel-call-export.sh /usr/local/sbin/ratel-call-export
   sudo install -m 0440 -o root -g root sudoers-ratel-meter.example /etc/sudoers.d/ratel-meter
   sudo visudo -cf /etc/sudoers.d/ratel-meter                     # parsed OK
   sudo -u ratelmeter sudo -n /usr/local/sbin/ratel-call-export --after-acc 0 --after-missed 0 --settle 10 | wc -l
   sudo -u ratelmeter sudo -n /usr/local/sbin/ratel-call-export --after-acc 0 --after-missed 0 --settle "1; DROP TABLE acc"; echo "exit $?"   # usage message, exit 2
   ```
   The first prints how many rows there are (nothing else leaves the VM). The last must refuse.
4. **The settings:**
   ```bash
   sudo install -d -m 0750 -o root -g ratelmeter /etc/ratel-meter
   sudo install -m 0600 -o ratelmeter -g ratelmeter ratel-meter-calls.env.example /etc/ratel-meter/ratel-meter-calls.env
   sudo -e /etc/ratel-meter/ratel-meter-calls.env       # the base URL (https://<bss-app>, no port) and the key; never in a chat
   ```
   Copy bss-app's certificate into `/etc/ratel-meter/trusted-certs.pem`, after checking its fingerprint on both
   sides (the same steps as core-up, `deploy/core-up/README.md`, step 5). The key is bss-app's `METER_API_KEY`.
5. **bss-app must let the voice VM in.** The nginx template has `location = /v1/calls`, which admits the voice VM
   and the office only. A host made from an older template gets it with
   `deploy/bss-app/nginx/add-pay-page-and-desk.py` (it takes the voice VM's address from `/v1/usage`).
6. **Try it once by hand, then start it:**
   ```bash
   sudo systemd-run --wait --pipe -p User=ratelmeter -p EnvironmentFile=/etc/ratel-meter/ratel-meter-calls.env \
     -p Environment=PYTHONPATH=/opt/ratel-meter/current/services \
     /opt/ratel-meter/current/venv/bin/python -m meter_agent.main --mode call --once; echo "exit $?"
   sudo cp ratel-meter-calls.service /etc/systemd/system/ && sudo systemctl daemon-reload
   sudo systemd-analyze verify /etc/systemd/system/ratel-meter-calls.service
   sudo systemctl enable --now ratel-meter-calls.service
   sudo journalctl -u ratel-meter-calls.service -f
   ```
   Make a call between two phones. About 70 seconds after it ends you should see `meter.calls.assembled`
   (`finished` 1) and `meter.poster.success`. On bss-app the call is on the line page's **Calls** tab.

## If it does not work

| In the journal | Likely cause |
| -------------- | ------------ |
| `meter.agent.tick_error` with `CallSourceError` | The export did not run: the sudo rule, the script path, or Docker/MySQL down. Run step 3's check by hand |
| `meter.poster.rejected` (401) | The key differs from bss-app's `METER_API_KEY` |
| `meter.poster.rejected` (403 or 444) | nginx does not admit the voice VM on `/v1/calls` (step 5) |
| `meter.poster.error` `ConnectError` | The certificate is not trusted (`SSL_CERT_FILE`), or the address is wrong |
| `meter.calls.rows_skipped` | The export printed a line the agent cannot read (a column was added or removed) |
| `meter.calls.open_calls_dropped` | An answered call with no hang-up for six hours: see the restart question in the call record agreement |

## Rules

Secrets live in owner-only environment files on the host, never here. Production changes go through reviewed
commits; nobody edits production by hand. A bad deploy here must never be able to take RatelCore down, which is why
business, voice and ops each have their own VM. Rollback: point `/opt/ratel-meter/current` at the previous release and
restart `ratel-meter-calls.service` (nothing is lost: the state file and the spool stay).

Owner: Network team (the VM). The agent's code is the RatelMeter owner's. TODO: confirm host details and how the
deployment credentials are handled.
