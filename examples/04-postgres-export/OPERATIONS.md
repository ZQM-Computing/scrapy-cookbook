# PostgreSQL backup and restore runbook

This runbook covers the optional PostgreSQL catalog sink in this cookbook. It is an operator procedure, not evidence that a production backup has been run or a restore has been rehearsed. Test it against a disposable database before relying on it.

## Scope and prerequisites

- PostgreSQL client utilities (`pg_dump`, `pg_restore`, `psql`) compatible with the server version.
- A database-administration identity authorized to read the catalog and create/restore into a separate target database.
- A protected backup directory with adequate capacity and access controls.
- Credentials supplied through a PostgreSQL service file, secret manager, or approved environment injection. Do not put passwords in shell history, command-line arguments, repository files, or logs.
- TLS certificate verification for remote connections; use `sslmode=verify-full` and a trusted root certificate.

The example table is `public.scraped_products`. These steps back up and restore the entire database, including schema and table data, rather than attempting a partial table-only recovery.

## 1. Create a consistent backup

Use a timestamped destination and fail if the output already exists:

```sh
set -eu
umask 077
: "${PGDATABASE:?Set PGDATABASE}"
: "${PGHOST:?Set PGHOST}"
: "${PGUSER:?Set PGUSER}"
backup_dir="${BACKUP_DIR:-./postgres-backups}"
mkdir -p "$backup_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$backup_dir/${PGDATABASE}-${stamp}.dump"
test ! -e "$backup"
pg_dump --format=custom --no-owner --no-acl --file="$backup"
test -s "$backup"
pg_restore --list "$backup" >/dev/null
(cd "$backup_dir" && sha256sum "$(basename "$backup")" > "$(basename "$backup").sha256")
(cd "$backup_dir" && sha256sum --check "$(basename "$backup").sha256")
```

Run this in an environment where libpq can obtain the approved connection details (for example, a protected service file or injected `PG*` settings). If the server is remote, configure TLS verification rather than disabling certificate checks.

Record the backup timestamp, server/database identity, PostgreSQL client/server versions, file size, checksum, and operator or job identity in the protected operations log. Store the dump and checksum separately from the database host, with encryption at rest and retention/access controls appropriate to the data.

A successful `pg_dump` and archive listing prove that a dump was created and can be read as an archive; they do not prove that it can be restored or that the backup meets a recovery-point objective.

## 2. Restore into a separate, empty database

Do not restore over the active database as a first recovery step. Create a new, empty target database using an administrator-approved process, then restore into it. The target connection details must point to that separate database.

```sh
set -eu
: "${PGHOST:?Set PGHOST}"
: "${PGUSER:?Set PGUSER}"
: "${RESTORE_DATABASE:?Set RESTORE_DATABASE to a newly created empty database}"
: "${BACKUP_FILE:?Set BACKUP_FILE to the selected dump}"
test -s "$BACKUP_FILE"
(cd "$(dirname "$BACKUP_FILE")" && sha256sum --check "$(basename "$BACKUP_FILE").sha256")
pg_restore --list "$BACKUP_FILE" >/dev/null
pg_restore --exit-on-error --no-owner --no-acl \
  --dbname="$RESTORE_DATABASE" "$BACKUP_FILE"
```

The `RESTORE_DATABASE` must already exist, be empty, and be isolated from production writes. The command intentionally omits `--clean` and does not drop objects in an existing database. If the restore fails, preserve the logs, discard or recreate the disposable target through the approved database-administration process, and diagnose before retrying.

## 3. Verify restored data

Connect to the restored database and run:

```sql
SELECT current_database(), current_timestamp;
SELECT count(*) AS product_count FROM public.scraped_products;
SELECT
    count(*) FILTER (WHERE url IS NULL) AS missing_url,
    count(*) FILTER (WHERE title IS NULL) AS missing_title,
    count(*) FILTER (WHERE extracted_at_utc IS NULL) AS missing_extraction_time,
    count(*) FILTER (WHERE first_seen_utc IS NULL) AS missing_first_seen_time
FROM public.scraped_products;
SELECT
    min(first_seen_utc) AS earliest_first_seen,
    max(first_seen_utc) AS latest_first_seen,
    min(extracted_at_utc) AS earliest_extraction,
    max(extracted_at_utc) AS latest_extraction
FROM public.scraped_products;
```

Compare the row count and time ranges with a trusted source captured near the backup time. For stronger validation, compare a deterministic, ordered digest or per-key counts computed on the source and restored databases; do not treat a count alone as proof that every row is identical. Verify required indexes, constraints, roles/grants, extensions, and application-specific dependencies separately. This runbook's `pg_dump --no-owner --no-acl` intentionally excludes original ownership and ACLs, so restore permissions must be provisioned deliberately.

Finally, start the application against the restored target only in a controlled test, using a least-privilege runtime role with schema auto-creation disabled. Confirm a known read and a controlled insert, then clean up the disposable target under the normal change-control process.

## 4. Automated recovery smoke test

The repository's GitHub Actions workflow runs `test_postgres_backup_restore.py` against the disposable PostgreSQL service. It creates isolated temporary source and target databases, inserts representative catalog records, creates a custom-format dump, checks the archive and SHA-256 digest, restores into the separate target, and compares all catalog columns plus the primary-key constraint and a representative index. The test drops its temporary databases afterward.

Run it locally only against a disposable PostgreSQL server with permission to create and drop databases, and with `pg_dump` and `pg_restore` installed:

```sh
export SCRAPY_POSTGRES_DSN='postgresql://test_user:test_password@localhost:5432/scrapy_test'
python -m unittest discover -s examples/04-postgres-export -p 'test_postgres_backup_restore.py' -v
```

Replace the example DSN with test-only credentials. The account must be able to connect to the maintenance database and create databases. The automated smoke test does not validate off-host backup storage, retention, production grants/roles, application secrets/configuration, or a deployment's actual RPO/RTO. It is not a substitute for a scheduled restore drill against the approved backup repository.

## 5. Recovery limitations and operating policy

- Define and approve the recovery-point objective (RPO), recovery-time objective (RTO), retention schedule, encryption, off-host/off-account storage, and restore-test cadence for the actual deployment.
- Keep schema migrations, database dumps, credentials, and application configuration under separate controls. A database dump does not replace configuration and secret recovery.
- A commit error can leave a write outcome uncertain. Before replaying a failed crawl item, reconcile its canonical URL against the restored/live table; the primary key prevents a duplicate row but a retry may be surfaced as a duplicate rather than a confirmed success.
- Backups are not verified until a restore into a separate target and data checks have succeeded. Record the tested backup identifier, restore duration, verification evidence, and any gaps.
- Do not use the integration-test DSN for this runbook. The automated integration suite drops and recreates `scraped_products`; only run it against a disposable test database.
