-- Read-only MySQL account for the app (run as an administrator; supply the password at run time).
-- The views must be created with SQL SECURITY DEFINER (the default) by the owner account.
CREATE USER 'gadgetgenie_reader'@'%' IDENTIFIED BY '<set from your secret manager>';
GRANT SELECT ON gadgetgenie.laptops TO 'gadgetgenie_reader'@'%';
GRANT SELECT ON gadgetgenie.phones TO 'gadgetgenie_reader'@'%';
ALTER USER 'gadgetgenie_reader'@'%' WITH MAX_QUERIES_PER_HOUR 2000;
