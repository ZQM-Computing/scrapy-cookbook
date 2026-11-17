# PostgreSQL recovery drill record

Use one copy of this template for each **authorized, non-production recovery drill**. Do not put passwords, tokens, private connection strings, customer records, or secret values in this record. Store completed records and supporting evidence in the approved restricted operations system, not in a public repository.

A blank template is not evidence that a drill occurred. Record actual timestamps and outcomes; use **Not tested** where a check was not performed.

## Drill identity

- Drill ID:
- Date (UTC):
- Operator / reviewer:
- Service and environment:
- Change / incident / exercise reference:
- Authorization and scope:
- Source backup identifier:
- Backup creation timestamp (UTC):
- Backup location identifier (no secret URL):
- Backup file size:
- Recorded SHA-256:
- PostgreSQL server version:
- pg_dump / pg_restore client versions:
- Approved RPO:
- Approved RTO:

## Recovery execution record

| Milestone | Start (UTC) | End (UTC) | Duration | Outcome / evidence reference |
| --- | --- | --- | --- | --- |
| Confirmed backup identity and access authorization | | | | |
| Verified checksum against independently stored manifest | | | | |
| Listed archive contents | | | | |
| Provisioned isolated, empty restore target | | | | |
| Restored database with fail-fast error handling | | | | |
| Verified row counts and representative records | | | | |
| Verified schema, constraints, indexes, and migration state | | | | |
| Provisioned and tested least-privilege runtime role | | | | |
| Verified required application configuration and secret references (without recording values) | | | | |
| Ran controlled application read/write smoke test | | | | |
| Removed disposable resources and confirmed cleanup | | | | |
| Reviewer accepted results and documented gaps | | | | |

## Validation results

- Backup checksum matches an independently stored expected value: Pass / Fail / Not tested
- Archive can be listed: Pass / Fail / Not tested
- Restore completed without errors: Pass / Fail / Not tested
- Expected row counts / key samples match trusted evidence: Pass / Fail / Not tested
- Required constraints, indexes, extensions, and schema version verified: Pass / Fail / Not tested
- Runtime identity can perform only intended operations: Pass / Fail / Not tested
- Application configuration and secret references are recoverable: Pass / Fail / Not tested
- Controlled application smoke test succeeded: Pass / Fail / Not tested
- Cleanup completed: Pass / Fail / Not tested

For data validation, record the query or test version, expected result, actual result, and a protected evidence reference. A row count alone does not prove full data equality. A checksum generated from the same file at the time of the drill is not an independent reference; compare with a checksum manifest protected separately from the backup.

## Results and corrective actions

- Actual recovery point / age of recovered data:
- Measured restore duration:
- RPO met: Yes / No / Not assessable
- RTO met: Yes / No / Not assessable
- Data loss or inconsistency found:
- Access-control or configuration gaps:
- Deviations from the approved runbook:
- Cleanup confirmation:
- Corrective action, owner, and due date:
- Reviewer decision and timestamp:

## Safety boundaries

- Use only a backup and target explicitly authorized for the drill.
- Restore to a separate isolated target; never test by overwriting the active database.
- Use test-only or approved recovery credentials. Do not store secrets in this record.
- Do not run the cookbook's destructive integration tests against a production DSN.
- A successful database restore does not establish recovery of roles, grants, application secrets, network routes, external services, or off-host backup retention unless those components were independently tested.
