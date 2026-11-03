-- Call records for RatelMeter's call agent: the extra columns on the S-CSCF's accounting tables.
-- Run in the `scscf` schema AFTER the tables exist (they come from the container's own script):
--
--   docker exec scscf cat /usr/local/share/kamailio/mysql/acc-create.sql | docker exec -i mysql mysql -uroot scscf
--   docker exec -i mysql mysql -uroot scscf < acc-columns.sql
--
-- Create these BEFORE restarting the S-CSCF with the configuration in scscf-acc.cfg.snippets: a column named in
-- `db_extra` that does not exist makes every record fail. Phone numbers are personal data (docs/call-record-agreement.md,
-- section 8): never SELECT these tables whole.
--
-- from_user / to_user: the user parts of the From and To headers (the number as dialled, so a phone may send 0XXXXXXXXXX
-- where a line's stored form is 234XXXXXXXXXX; the agent normalises).
-- start_ts: epoch seconds (UTC) when the INVITE (or BYE) arrived at the S-CSCF. `time` is when the final reply passed.

ALTER TABLE acc
  ADD COLUMN from_user VARCHAR(64)  NOT NULL DEFAULT '',
  ADD COLUMN to_user   VARCHAR(64)  NOT NULL DEFAULT '',
  ADD COLUMN start_ts  INT UNSIGNED NOT NULL DEFAULT 0;

ALTER TABLE missed_calls
  ADD COLUMN from_user VARCHAR(64)  NOT NULL DEFAULT '',
  ADD COLUMN to_user   VARCHAR(64)  NOT NULL DEFAULT '',
  ADD COLUMN start_ts  INT UNSIGNED NOT NULL DEFAULT 0;
