-- Read-only account for the app. Run as the schema owner after `gadgetgenie seed --postgres <owner dsn>`.
-- Pass the password at run time (psql -v reader_password=...); never commit it.
CREATE ROLE gadgetgenie_reader LOGIN PASSWORD :'reader_password';
ALTER ROLE gadgetgenie_reader SET default_transaction_read_only = on;
ALTER ROLE gadgetgenie_reader SET statement_timeout = '5s';
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM gadgetgenie_reader;
GRANT USAGE ON SCHEMA public TO gadgetgenie_reader;
-- only the two views; the base tables stay invisible to the app
GRANT SELECT ON laptops, phones TO gadgetgenie_reader;
