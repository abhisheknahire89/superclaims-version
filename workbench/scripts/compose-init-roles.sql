-- Development roles for docker-compose.yml (same roles as scripts/dev_db.sh). Neither role can bypass row-level security.
CREATE ROLE aw_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'dev-only-app-pw';
CREATE ROLE aw_worker LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'dev-only-worker-pw';
