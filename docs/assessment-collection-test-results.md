# Assessment Postman collection verification

Executed against a disposable PostgreSQL cluster and a real HTTP API server.
All 22 collection requests covered; browser requests checked with doctor and owner tokens.
Passwords, JWT verification, roles, permissions and SQL were real; no authentication overrides.
Patient activation was simulated in the disposable DB after checking pending access is denied.
Localhost:8000 credentials were unavailable; this report does not claim that deployment passed.

| Request | Expected/actual HTTP |
|---|---|
| Doctor login | 200 / 200 |
| Platform owner login | 200 / 200 |
| Patient login | 200 / 200 |
| 02 All categories | 200 / 200 |
| 03 All sub-categories | 200 / 200 |
| 04 Sub-categories by category | 200 / 200 |
| 05 All assessments | 200 / 200 |
| 06 Assessments by category | 200 / 200 |
| 07 Assessments by sub-category | 200 / 200 |
| 08 Find imported assessment by code | 200 / 200 |
| 09 Assessment metadata and versions | 200 / 200 |
| 10 Version counts and pricing | 200 / 200 |
| 11 Domains | 200 / 200 |
| 12 All sub-domains | 200 / 200 |
| 13 Sub-domains by domain | 200 / 200 |
| 14 Questions options and weightage | 200 / 200 |
| 15 Questions by domain | 200 / 200 |
| 16 Questions by sub-domain | 200 / 200 |
| 17 Questions by domain and sub-domain | 200 / 200 |
| 02 All categories | 200 / 200 |
| 03 All sub-categories | 200 / 200 |
| 04 Sub-categories by category | 200 / 200 |
| 05 All assessments | 200 / 200 |
| 06 Assessments by category | 200 / 200 |
| 07 Assessments by sub-category | 200 / 200 |
| 08 Find imported assessment by code | 200 / 200 |
| 09 Assessment metadata and versions | 200 / 200 |
| 10 Version counts and pricing | 200 / 200 |
| 11 Domains | 200 / 200 |
| 12 All sub-domains | 200 / 200 |
| 13 Sub-domains by domain | 200 / 200 |
| 14 Questions options and weightage | 200 / 200 |
| 15 Questions by domain | 200 / 200 |
| 16 Questions by sub-domain | 200 / 200 |
| 17 Questions by domain and sub-domain | 200 / 200 |
| Assign assessment to linked patient | 201 / 201 |
| My assessment assignments | 200 / 200 |
| My assigned questions and options | 403 / 403 |
| My assigned questions and options | 200 / 200 |
| 02 All categories | 403 / 403 |
| My assigned questions and options | 404 / 404 |
| My assigned questions and options | 403 / 403 |
