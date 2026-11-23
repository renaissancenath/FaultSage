---
name: faultsage-migrations
description: Use for any FaultSage database change, local SQLite or cloud PostgreSQL, and whenever someone asks to clean up, drop, rename or delete tables, columns or rows. Enforces the destructive-migration approval gate.
---

# FaultSage database changes

Read `docs/DATABASE.md` section 4 and `docs/security/01_SECURITY-RULES.md` SR-26 and SR-28 first.

## Safe changes (add table, add nullable column, add index)
1. Add the next numbered file: `src/faultsage/storage/migrations/NNNN_name.sql` (local) or
   `src/faultsage/cloud/storage/migrations/NNNN_name.sql` (cloud; use `{{ID}}` for primary keys).
2. Never edit an applied migration. Add a test that runs the migration on a fresh database.
3. Safe migrations apply on start.

## Destructive changes ("clean up unused tables")
1. Find what is unused with evidence (grep for table names in `storage/`, row counts if you have
   read access). List every table or column and the data that would be lost.
2. Write `NNNN_name_destructive.sql`. The loader refuses destructive SQL in any other file name.
3. STOP. Show the engineer the file, the list, and the data impact. Ask for approval for this
   migration in this environment. Record the question in `docs/DECISIONS.md` if they are away.
4. Running it is the engineer's call, every time, per environment:
   - local: `faultsage db migrate --approve NNNN` (typed confirmation, automatic backup)
   - cloud: `faultsage-cloud db migrate --approve NNNN --env production --approved-by NAME`
     (typed confirmation, pg_dump backup, row in `migration_approvals`)
5. Approval for one migration never covers the next one, or the same one in another environment.
   The repository hook `tools/hooks/destructive_gate.py` asks again on every destructive call.
6. Quote the engineer's approval in the PR.
