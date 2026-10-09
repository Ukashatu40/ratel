"""RatelMeter agent. Data mode on core-up, call mode on voice. Scaffold only.

See services/meter_agent/README.md. Planned layout (docs/adr/0008): sources/ (read counters and call
records), domain/ (interval alignment, counter delta and reset, joining call start and end: pure),
spool/ (disk spool and ordered replay), client/ (post batches, read RatelLink assignments),
runners/ (the data-mode and call-mode loops), main.py and config.py as entry point and settings.
"""
