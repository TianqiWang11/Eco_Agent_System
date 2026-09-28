-- Run once as the database owner (for example postgres) in database chebaling.
-- Allows the application login to create the two additional public tables.
GRANT USAGE, CREATE ON SCHEMA public TO chebaling;
