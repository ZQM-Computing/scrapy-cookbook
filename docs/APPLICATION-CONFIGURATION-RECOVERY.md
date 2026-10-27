# Application configuration and secret recovery

This guide defines a safe, provider-neutral process for recovering the configuration needed to run the Scrapy PostgreSQL example. It is an inventory and operator procedure, not proof that any specific deployment stores or backs up these values. Adapt it to the deployment's approved secret manager, configuration repository, identity system, and change-control process.

## Recovery boundary

A PostgreSQL dump restores database objects and data included in the archive. It does not, by itself, restore or validate:

- Scrapy settings and pipeline registration;
- runtime environment variables and secret-manager references;
- database roles and grants when the backup is created with `--no-owner --no-acl`;
- CA certificates, TLS policy, DNS, firewall rules, network routes, or service discovery;
- Python runtime, pinned dependencies, OS packages, scheduled jobs, or deployment manifests;
- access policies, workload identities, external APIs, monitoring, or alerting.

Treat these as separate recovery dependencies and test them separately. Never put actual passwords, tokens, private keys, connection strings, certificate private material, or production values in this repository or a drill record.

## 1. Maintain a deployment inventory

Store the completed inventory in the approved restricted operations system. Track references and owners, not secret values.

| Component | Inventory fields | Recovery evidence |
| --- | --- | --- |
| Application artifact | Repository, immutable commit/tag, build identifier | Artifact can be retrieved and verified |
| Runtime | Python version, Scrapy/psycopg lock or requirements files, OS/client dependencies | Clean environment installs pinned dependencies |
| Scrapy configuration | Settings module, enabled pipelines, crawler limits, schema-auto-create setting | Effective settings reviewed with secrets redacted |
| Database endpoint | Secret-manager key/reference, hostname/service identifier, port, database name | Endpoint resolves and is reachable from the approved runtime |
| Database identity | Workload identity or secret reference, required grants, owner/contact | Runtime identity authenticates and only required operations succeed |
| TLS | Required verification mode, CA bundle reference, certificate renewal owner | Verified TLS connection succeeds; invalid/untrusted certificate fails closed |
| Schema | Migration directory/version, expected tables, constraints, indexes, extensions | Migration state and required objects verified after restore |
| Network and DNS | Service names, route/firewall policy references, private connectivity dependencies | Approved connectivity checks pass without exposing private topology publicly |
| Scheduling | Job/worker definitions, schedule, concurrency and retry policy | Job can be safely enabled in a test environment |
| Observability | Log destination, health checks, alerts, on-call owner | Test event and failure signal are visible to authorized operators |
| External integrations | Service identifiers, auth references, scopes, rate limits | Non-destructive test request succeeds |

## 2. Recover configuration without exposing secrets

1. Confirm the incident/change authorization, recovery scope, target environment, and accountable operator.
2. Retrieve the approved immutable application artifact and its versioned, non-secret configuration from their authoritative sources.
3. Re-establish access to the approved secret manager or workload identity. Retrieve secret values at runtime only; do not copy them into Git, tickets, terminal transcripts, CI logs, screenshots, or this checklist.
4. Reissue a credential only when recovery requires it and the authorized owner approves it. Credential rotation is a separate controlled change, not an automatic recovery step.
5. Restore CA certificates and trust configuration from approved sources. Validate certificate identity and chain; do not disable TLS verification to make a recovery test pass.
6. Apply schema migrations using a dedicated migration identity. Configure the crawler runtime with `POSTGRES_AUTO_CREATE_TABLE=False` and a least-privilege role for routine inserts/reads.
7. Verify the effective runtime settings with sensitive values redacted. Check that no fallback or default silently targets production during a recovery exercise.
8. Start the application only against an isolated restore target until the reviewer authorizes the next stage.

## 3. Validate service dependencies in order

Run these checks from the same network boundary and runtime identity intended for the application. Record timestamps, result, and a protected evidence reference; do not record secret values or unnecessary sensitive topology.

1. **Artifact:** expected commit/build is present and integrity verified.
2. **Configuration:** required non-secret settings exist; mandatory secret references resolve; no production endpoint is accidentally selected.
3. **DNS and routing:** configured database hostname resolves through the intended resolver and approved route.
4. **TLS:** connection uses certificate verification (for remote PostgreSQL, normally `sslmode=verify-full` with the expected CA and hostname).
5. **Authentication:** workload identity or secret reference authenticates successfully.
6. **Authorization:** runtime identity can perform the minimum required operation and is denied schema DDL or unrelated privileged operations.
7. **Schema:** expected migration version, columns, constraints, and indexes are present.
8. **Application smoke test:** a controlled read and uniquely identified test insert succeed; test data is clearly marked and removed where safe.
9. **Observability:** success and an intentionally induced, non-destructive failure are visible in logs/alerts.
10. **Cleanup:** test resources and temporary permissions are removed, and the operator verifies cleanup.

Do not run destructive integration tests against a production DSN. This cookbook's PostgreSQL integration tests drop and recreate `scraped_products`; its backup/restore smoke test creates and drops temporary databases. Use disposable infrastructure only.

## 4. Recovery acceptance criteria

Do not declare the service recovered solely because PostgreSQL starts or a dump restores. The responsible operator and reviewer should verify:

- [ ] Database restore and data/schema validation succeeded.
- [ ] Application artifact and dependencies match the approved version.
- [ ] Required configuration and secret references are available without secrets being exposed.
- [ ] Network path and TLS identity are verified.
- [ ] Least-privilege authentication and authorization checks passed.
- [ ] Controlled application read/write smoke test passed.
- [ ] Monitoring and failure visibility are operational.
- [ ] Actual recovery point and elapsed recovery time were recorded against approved RPO/RTO.
- [ ] Temporary resources and privileges were cleaned up.
- [ ] Remaining gaps have named owners and due dates; reviewer acceptance is recorded.

A successful test against a disposable environment does not prove that production secret recovery, backup retention, identity policies, external services, or disaster-recovery objectives work. Keep evidence scoped to the environment and components actually tested.
