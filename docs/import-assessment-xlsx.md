# Import assessment workbooks

Run from the repository root, using Python with `psycopg` 3 and `python-dotenv` installed. XLSX reading uses Python's standard library; no Excel dependency is needed. Platform migrations through V031 must already be applied. The script does not run migrations.

Optional Bio column `assessment_subcategory` creates/reuses a separate sub-category within
`assessment_category` and links the assessment to it. Blank or missing values clear the
assessment's sub-category on re-import. Existing workbooks remain valid without this column.

```bash
python3 scripts/import_assessment_xlsx.py /path/to/folder --validate-only
python3 scripts/import_assessment_xlsx.py /path/to/folder --dry-run
python3 scripts/import_assessment_xlsx.py /path/to/folder
```

Only immediate `.xlsx` files are processed, in filename order; Excel lock files (`~$...`) are skipped. Each file has its own transaction. Failure rolls back that file and stops by default; previously committed files remain committed. `--continue-on-error` processes subsequent files and still exits nonzero if any file failed. Dry run rolls back each workbook. Validation-only makes no database connection.

The first worksheet must have one Bio record and the second must contain questions, with headers in their first nonempty rows. Later worksheets are ignored. Assessment identity comes from Bio `assessment_id`, not the filename. Duplicate assessment codes within the folder are rejected. Formulas and nonempty images are rejected instead of silently losing data.

| Source | Destination |
| --- | --- |
| Bio assessment_category | assessment_categories (reuse by name) |
| Bio assessment_id, name and metadata | assessments (code, name and metadata columns) |
| Bio assessment_duration | assessment_versions.duration_minutes |
| Bio assessment_cost | assessment_pricing.price |
| Questions domain | assessment_sections.name |
| Questions sub_domain | assessment_dimensions.name; domain also retained in description |
| Questions question, sr_no | questions.question_text, display_order within domain section |
| option_N | question_options.option_text; N as display_order and option_value |
| weightage_N | question_option_scores.score, linked to that question's sub-domain dimension |

The default target version is 1; select another using `--version 2`. Existing target versions must be DRAFT. Options are SINGLE_CHOICE. Sections are ordered by first domain occurrence in serial-number order. Sub-domain codes are stable hashes of domain plus sub-domain; dimensions are flat, without a parent-child schema change. This importer creates sub-domain scores, not separate domain/total score rules. Interpretation and Descriptor sheets are not imported.

Options are dynamic, with no four-option limit. Each supplied option requires its matching weightage. Fully blank pairs are ignored, zero is valid, and the literal Excel text `None` remains an option label. Scores allow negative values, with at most two decimals within NUMERIC(10,2). Blank Bio metadata becomes null; blank cost leaves pricing unchanged. Non-null new prices require the actual split, e.g. `--doctor-percentage 70` (example only). Existing pricing history is handled by the shared metadata importer.

Repeated imports preserve IDs using existing unique keys. Preserve domain order and serial numbers when editing a workbook. Removing existing sections/questions/options/dimensions or changing scoring dimension membership is rejected: use a new assessment version. Existing unrelated content in the target version may therefore cause a conflict instead of being overwritten or deleted.

Database settings come from the root `.env`: `PLATFORM_DB_HOST`, `PLATFORM_DB_PORT`, `PLATFORM_DB_NAME`, `PLATFORM_DB_USER`, `PLATFORM_DB_PASSWORD`.
