# RatelLink lab acceptance, first run (record)

Follows [the runbook](../runbooks/ratel-link-lab-acceptance.md), section 6. A SIM is identified by the last four digits of
its IMSI only. Not finished: the rows marked TODO are for the next run.

| | |
| --- | --- |
| Date and time (Lagos) | 2026-11-04 afternoon (first SIM) and 2026-11-05 afternoon (second SIM). Core log times are UTC |
| Who ran it, and who from the network team was present | The project lead. The network lead was present for the first hour of 2026-11-04 and then left; the rest was done alone |
| SIM (last four digits of the IMSI) | First: TODO (ends in 451, sold through RatelDesk). Second, a spare imported and activated directly: 0452 |
| Phone model and OS | TODO (a smartphone for data, a keypad phone for calls) |
| RatelLink release (`/opt/ratel-link/current` target) | TODO |
| Step 1 template comparison | Not run in this session. TODO |
| Steps 2 and 3 | First SIM: import 200, activation from RatelDesk (line `active`). Second SIM: import 200, activation 200 (after a 404 because the import was skipped, and a 422 for a placeholder number) |
| 4.1 attach | Pass after the APN was set to `internet`. Before that the phone showed emergency calls only |
| 4.2 browse | **Not passed.** The phone attached and sent packets but nothing came back: core-up had no internet access that day. Uplink restored later on 2026-11-05. TODO: retest |
| 4.3 IMS registration | Pass (calls were placed and recorded) |
| 4.4 call | Pass: calls between the lab phones, shown in RatelDesk's Calls tab with their numbers, ring time, talk time and result (answered, caller hung up before it was answered, could not be reached) |
| 4.5 data off, calls still work | Not run. TODO |
| 4.6 data on | Not run. TODO |
| 4.7 deactivate rejects the SIM | Not run. TODO (spare SIM, second one, is ready) |
| 4.8 re-activate attaches again | Not run. TODO. Decides DECISIONS_PENDING item 52 |
| 5 log search | 0 matches (RatelLink's journal for the first SIM's Ki and OPc, 2 hours) |
| Blockers and their owners | Browse retest (project lead, with the uplink back); 4.5 to 4.8 (project lead); template comparison (project lead) |

Also checked on 2026-11-05: the RatelLink encryption key's offline copy decrypts to the live key (SHA-256 of both equal);
the passphrase is kept apart from the file.
