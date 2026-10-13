# Assessment JSON import

Run from the repository root using the Python environment containing `psycopg`
(version 3) and `python-dotenv`. Requires platform migrations through V030.
Uses `PLATFORM_DB_HOST`, `PLATFORM_DB_PORT`, `PLATFORM_DB_NAME`,
`PLATFORM_DB_USER`, `PLATFORM_DB_PASSWORD` from the environment or root `.env`.

Save a valid JSON object or array in `assessments.json` (without HTML entities,
escaped underscores, or trailing commas).

```bash
python scripts/import_assessments.py assessments.json --validate-only
python scripts/import_assessments.py assessments.json --dry-run
python scripts/import_assessments.py assessments.json
```

For a new non-null price, supply your actual revenue split:

```bash
python scripts/import_assessments.py assessments.json --doctor-percentage 70
```

Here 70 is an example, not a default; the platform receives the remainder.
An existing price's split is preserved unless this option is supplied.

| Input | Destination |
| --- | --- |
| assessment_id | assessments.code (internal UUID remains separate) |
| assessment_category | assessment_categories.name, linked by category_id |
| assessment_name | assessments.name |
| assessment_full_name | assessments.full_name |
| copyright, description, min_age, max_age, typical_groups | Same columns in assessments |
| charts | assessments.charts, converted from comma-separated text to JSON array |
| domain_charts, t_score, domain_t_score | Same columns in assessments, Y/N converted to booleans |
| assessment_duration | assessment_versions.duration_minutes |
| assessment_cost | assessment_pricing.price, currency INR |

Age bounds are required nonnegative integers with min_age <= max_age, in years.
Duration must be a positive integer in minutes. Age and duration values must be
JSON numbers, not quoted strings. Unknown fields and duplicate assessment IDs
within a batch are rejected before connecting.

Version 1 is the default target; use `--version 2` to target version 2 instead.
New assessments/versions retain the DB default DRAFT status. Existing statuses
are preserved, including published status: importing updates the selected
version's duration and shared assessment metadata.

Categories are matched case-insensitively by name; new category codes are
generated from uppercase names with underscores. Ambiguous names or code
collisions fail rather than linking to a different category.

Omitted optional metadata is preserved on update. Explicit null clears optional
metadata; blank strings become null. Null/omitted assessment_cost leaves pricing
unchanged, and creates no pricing row for a new assessment. Zero is a valid price.
Changed prices close the previous active price and insert a new row to retain
history. Multiple active/scheduled prices and conflicting scheduled price changes
require manual resolution. Identical prices are not duplicated.

The entire batch uses one transaction: any failure rolls back all its changes.
`--dry-run` performs the database writes and validations but rolls back the
transaction. `--validate-only` checks input without database access; it cannot
validate migration state, existing categories, or pricing configuration.
