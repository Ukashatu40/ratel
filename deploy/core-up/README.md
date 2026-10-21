# deploy/core-up

RatelCore user plane host. Runs the **meter_agent** in data mode.

## Installation

1. Create the system user and group:
   ```bash
   sudo useradd -r -s /usr/sbin/nologin ratelmeter
   ```

2. Create the directories with restricted permissions:
   ```bash
   sudo mkdir -p /opt/ratel-meter/current /etc/ratel-meter /var/spool/ratel-meter /var/run/ratel-meter
   sudo chown -R ratelmeter:ratelmeter /opt/ratel-meter /etc/ratel-meter /var/spool/ratel-meter /var/run/ratel-meter
   sudo chmod 0700 /etc/ratel-meter /var/spool/ratel-meter
   ```

3. Deploy code and dependencies into `/opt/ratel-meter/current` with Python 3.12 venv.

4. Install configuration:
   ```bash
   sudo cp deploy/core-up/ratel-meter.env.example /etc/ratel-meter/ratel-meter.env
   sudo chmod 0600 /etc/ratel-meter/ratel-meter.env
   sudo chown ratelmeter:ratelmeter /etc/ratel-meter/ratel-meter.env
   # Edit /etc/ratel-meter/ratel-meter.env with real tokens
   ```

5. Install and start the systemd unit:
   ```bash
   sudo cp deploy/core-up/ratel-meter.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now ratel-meter.service
   ```

## Verification

Check service status and logs:
```bash
sudo systemctl status ratel-meter.service
sudo journalctl -u ratel-meter.service -f
```

Refer to [docs/runbooks/ratel-meter.md](../../docs/runbooks/ratel-meter.md) for diagnostics and troubleshooting.
