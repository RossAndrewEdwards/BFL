# Multi-League Migration Runbook

## Purpose

This runbook defines how to migrate the current Invicta fantasy app database into the multi-league model safely, and how to roll back if something goes wrong.

It is written for the current Flask + SQLite app in this repository.

Primary database:

- `C:\Users\reods\Desktop\invicta_fantasy_webapp\league.db`

Primary app entrypoint:

- `C:\Users\reods\Desktop\invicta_fantasy_webapp\app.py`

## Current Migration Scope

The migration now covers:

- seeded `leagues` table with default `Invicta` league
- `league_id` backfill on league-scoped records
- role expansion to:
  - `site_admin`
  - `league_admin`
  - `player`
- league-aware query and route scoping

## Risks This Runbook Covers

- partial schema migration
- failed role migration
- missing `league_id` backfills
- broken login or permission behavior after migration
- app startup failures after schema change

## Preconditions

Before running migration on any live-style database:

- stop manual edits to the site during the migration window
- confirm the current `league.db` file path
- confirm the app test suite is green in the current code
- confirm you have enough disk space for at least two full database copies

## Pre-Migration Checklist

1. Verify the codebase is the intended version.
2. Run the test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

3. Confirm the app boots locally before migration.
4. Record the current timestamp for the migration log.
5. Create a backup folder if it does not already exist:

```powershell
New-Item -ItemType Directory -Force -Path .\backups
```

## Backup Procedure

Create two backups before running any migration:

1. A timestamped raw copy.
2. A second rollback copy kept untouched unless recovery is required.

Example:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item .\league.db ".\backups\league-$stamp-pre-multileague.db"
Copy-Item .\league.db ".\backups\league-$stamp-rollback.db"
```

After copying:

- confirm both files exist
- confirm file sizes are non-zero

Example:

```powershell
Get-ChildItem .\backups\league-$stamp-*.db | Select-Object Name, Length, LastWriteTime
```

## Recommended Dry Run

Before touching the main database, test the migration on a throwaway copy:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item .\league.db ".\backups\league-$stamp-dryrun.db"
```

Temporarily point the app at the dry-run database, then start the app and let the existing startup migration logic run. Afterward, verify:

- `leagues` contains the default Invicta row
- `users.role` allows `site_admin`, `league_admin`, and `player`
- all league-scoped rows have non-null `league_id` where expected

## Migration Execution

For this app, the migration is currently performed by the startup initialization path in `app.py` and `db_support.py`.

Recommended execution order:

1. Ensure the backup is complete.
2. Start the app against the target database.
3. Let app startup run the migration.
4. Stop the app if any migration error appears.

Example:

```powershell
.\.venv\Scripts\python.exe .\app.py
```

## Post-Migration Verification

Run the automated test suite again:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Then manually verify the database.

### 1. Confirm league seed

```powershell
@'
import sqlite3
conn = sqlite3.connect("league.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, slug, name, status FROM leagues ORDER BY id").fetchall()
for row in rows:
    print(dict(row))
'@ | .\.venv\Scripts\python.exe -
```

Expected:

- at least one row exists
- default seeded row includes `slug = invicta`

### 2. Confirm admin role migration

```powershell
@'
import sqlite3
conn = sqlite3.connect("league.db")
print(conn.execute("SELECT username, role, league_id FROM users WHERE username='admin'").fetchone())
'@ | .\.venv\Scripts\python.exe -
```

Expected:

- admin user exists
- role is `site_admin`
- `league_id` is populated

### 3. Confirm scoped tables are backfilled

```powershell
@'
import sqlite3
conn = sqlite3.connect("league.db")
checks = [
    ("users", "SELECT COUNT(*) FROM users WHERE league_id IS NULL"),
    ("fighters", "SELECT COUNT(*) FROM fighters WHERE league_id IS NULL"),
    ("event_results", "SELECT COUNT(*) FROM event_results WHERE league_id IS NULL"),
    ("fantasy_teams", "SELECT COUNT(*) FROM fantasy_teams WHERE league_id IS NULL"),
    ("claim_tokens", "SELECT COUNT(*) FROM claim_tokens WHERE league_id IS NULL"),
]
for name, sql in checks:
    print(name, conn.execute(sql).fetchone()[0])
'@ | .\.venv\Scripts\python.exe -
```

Expected:

- zero null `league_id` rows for the migrated core tables

### 4. Verify app behavior

Minimum manual checks:

- homepage loads
- site admin can log in
- `/admin/fighters` loads
- `/admin/events` loads
- `/admin/players` loads
- `/admin/teams` loads

## Failure Conditions

Treat the migration as failed if any of these happen:

- app startup raises a schema or foreign key error
- `users` role migration does not complete
- default league is missing
- core scoped rows are left without `league_id`
- admin login or main admin routes stop working

## Rollback Procedure

If migration fails, do not try to repair the live database by hand first.

Recommended rollback:

1. Stop the app.
2. Preserve the failed migrated database for debugging.
3. Restore the untouched rollback copy.
4. Re-run the app on the restored database only after the code issue is fixed.

Example:

```powershell
$stamp = "REPLACE_WITH_TIMESTAMP"
Copy-Item ".\backups\league-$stamp-rollback.db" .\league.db -Force
```

After restoring:

- confirm `league.db` timestamp changed
- start the app
- verify the pre-migration behavior is back

## Rollback Validation

After rollback:

- site loads
- admin login works
- fighters, teams, rules, and events pages load
- no schema mismatch error appears in app startup

## Incident Notes Template

If migration fails, record:

- migration timestamp
- git revision or working copy description
- backup filenames used
- exact error message
- whether rollback completed successfully
- whether any manual data edits were made

## Next Step After This Runbook

Once this runbook is accepted, the next implementation step should be:

- `BL-006 Site-admin league management screens`

That gives the site owner an actual UI for creating and managing leagues instead of relying on direct database edits.
