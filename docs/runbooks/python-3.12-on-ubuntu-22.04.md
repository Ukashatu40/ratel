# Runbook: Python 3.12 on an Ubuntu 22.04 host

Keep it short. Never put a key, a token or real customer data in a ticket, a chat message or this file.

- **Last verified:** 2026-10-22 on core-up (Python 3.12.15). The same method was used on core-cp earlier.
- **Owner:** @Ukashatu40
- **Why:** Ubuntu 22.04 ships Python 3.10, and the services need 3.12. The python.org source is built and
  installed with `make altinstall` under `/opt/python-3.12`, so the system Python is not touched. No third-party
  package source (such as a PPA) is added to the host.

## Steps

1. **Build tools.** Standard Ubuntu packages. On a host that runs services (core-up runs the UPF), list the
   restarts instead of doing them, and never tick `open5gs-*` in a restart dialog:
   ```bash
   sudo NEEDRESTART_MODE=l apt install -y build-essential curl libssl-dev zlib1g-dev libbz2-dev \
     libreadline-dev libsqlite3-dev libffi-dev liblzma-dev libncurses-dev uuid-dev
   ```
   Install `uuid-dev` before `./configure`, or the `_uuid` module is skipped (harmless here).

2. **Download and verify, in a new empty folder.** The signature is checked against the release manager's
   key, fetched from a keyserver:
   ```bash
   mkdir ~/py-build && cd ~/py-build
   PYVER=3.12.15
   curl -fsSLO "https://www.python.org/ftp/python/$PYVER/Python-$PYVER.tgz"
   curl -fsSLO "https://www.python.org/ftp/python/$PYVER/Python-$PYVER.tgz.asc"
   gpg --keyserver hkps://keyserver.ubuntu.com --recv-keys 7169605F62C751356D054A26A821E680E5FA6305
   gpg --verify "Python-$PYVER.tgz.asc" "Python-$PYVER.tgz"
   ```
   Required: `Good signature from "Thomas Wouters ..."` and the primary key fingerprint
   `7169 605F 62C7 5135 6D05  4A26 A821 E680 E5FA 6305`. The warning "not certified with a trusted
   signature" is normal. Anything saying `BAD signature`: stop and tell the project lead.
   Check the current version and key on python.org/downloads before reusing this for a newer release.

3. **Build.** Use at most two low-priority jobs on a host that carries traffic:
   ```bash
   tar -xzf "Python-$PYVER.tgz" && cd "Python-$PYVER"
   ./configure --prefix=/opt/python-3.12 --with-ensurepip=install
   nice -n 19 make -j2
   sudo make altinstall
   ```
   The list of modules "not built" (`_dbm`, `_gdbm`, `_tkinter`, `nis`) is expected and harmless.

4. **Check, then clean up.** `make altinstall` leaves root-owned files in the source folder:
   ```bash
   /opt/python-3.12/bin/python3.12 --version
   /opt/python-3.12/bin/python3.12 -m venv /tmp/v312 && /tmp/v312/bin/pip --version && rm -rf /tmp/v312
   cd ~ && sudo rm -rf ~/py-build
   ```

Use the full path `/opt/python-3.12/bin/python3.12` (for example as the second argument of
`install-release.sh`). It is not on `PATH` on purpose.

## Rollback

Nothing else depends on it until a service is installed with it. To remove it: `sudo rm -rf /opt/python-3.12`.
A service that was installed with it keeps its own virtualenv, which points at this path, so remove the
service first.
