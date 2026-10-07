# RatelOps configuration

Owned by the **Network team**. Prometheus, Grafana and Alertmanager on the `ops` VM. Configuration,
not application code. Starts in Week 4; alarms and the demo dashboard in Week 5.

Open5GS's MME and SMF export Prometheus metrics, Kamailio has a Prometheus module, node_exporter
covers each machine, and a radio counts as up when the MME sees it connected. Alerts go to the
network team by email and one messaging channel the team picks. TODO: channel.

No secrets in this directory (SMTP and webhook credentials live in environment files on the host).
