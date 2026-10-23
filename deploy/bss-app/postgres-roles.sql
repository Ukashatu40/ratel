-- PostgreSQL roles for the app on bss-app. Run once, as the postgres superuser, on the bss-app host:
--
--   sudo -u postgres psql -v ON_ERROR_STOP=1 -f postgres-roles.sql
--
-- Two roles, so a bug or a leaked runtime password cannot change the schema:
--   ratel_owner  owns the database and runs the migrations. Used only by hand, never by the service.
--   ratel_app    the service's role: read and write rows, nothing else.
-- No password is in this file. Set each one afterwards with `\password <role>` in psql, which
-- prompts and never puts the password in a command line, a file or the shell history.

CREATE ROLE ratel_owner LOGIN;
CREATE ROLE ratel_app LOGIN;
CREATE DATABASE ratel_bss OWNER ratel_owner;
REVOKE ALL ON DATABASE ratel_bss FROM PUBLIC;
GRANT CONNECT ON DATABASE ratel_bss TO ratel_app;

\connect ratel_bss

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO ratel_app;

-- Tables and sequences the migrations create later. The ledger's triggers still refuse UPDATE,
-- DELETE and TRUNCATE on ledger rows whatever these grants say (ADR 0009).
ALTER DEFAULT PRIVILEGES FOR ROLE ratel_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ratel_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ratel_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ratel_app;
