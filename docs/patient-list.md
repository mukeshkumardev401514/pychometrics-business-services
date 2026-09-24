# Patient list counts

`GET /data/patients?limit=20&offset=0` returns `items`, existing top-level
`limit` and `offset`, plus `pagination` and `counts`:

```json
{
  "counts": {"total_patients": 100, "active": 100, "in_progress": 0, "not_started": 0},
  "pagination": {"limit": 20, "offset": 0, "total": 100, "total_pages": 5},
  "items": [],
  "limit": 20,
  "offset": 0
}
```

Counts cover the authorized patient set, independent of pagination. Doctors see
their actively linked patients; hospital admins see their tenant's patients.
Patient users see only themselves. Existing permission checks still apply.

- `total_patients`: all visible patients.
- `active`: visible patients whose patient status is `ACTIVE`.
- `in_progress`: visible patients with at least one `IN_PROGRESS` assessment assignment.
- `not_started`: visible patients with a `PENDING_PAYMENT` or `ASSIGNED` assignment
  and no `IN_PROGRESS` assignment.

Multiple assignments never multiply patient counts. Patients without assignments
are excluded from both assessment counts. Active and assessment counts can overlap;
these are not mutually exclusive categories. Empty sets return zero counts and
zero total pages. An offset beyond the final page returns empty items with the
full counts retained. Counts and page rows use separate database reads, so concurrent
writes can change the dataset between those reads.
