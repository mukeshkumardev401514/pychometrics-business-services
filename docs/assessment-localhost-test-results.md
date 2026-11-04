# Localhost assessment API check

Actual doctor login against localhost:8000. No assessment/patient data modified.
Owner and patient login credentials were not provided; those workflows were tested separately on disposable databases.
Sub-category IDs were unavailable; a nonexistent UUID was used for that filter.
Retested after the user applied V031: all 17 doctor login/browser requests returned HTTP 200.
Version IDs came from the assessment metadata response.
Returned data: 1 category, 1 assessment, 2 domains, 4 sub-domains and 48 questions.
There are currently no sub-categories; listing and filtering correctly return empty lists.

| Request | Actual HTTP |
|---|---|
| Doctor login | 200 |
| All categories | 200 |
| All sub-categories | 200 |
| All assessments (original failing URL) | 200 |
| Find assessment by code | 200 |
| Sub-categories by category | 200 |
| Assessments by category | 200 |
| Assessments by sub-category (nonexistent ID) | 200 |
| Assessment metadata and versions | 200 |
| Version counts and pricing | 200 |
| Domains | 200 |
| All sub-domains | 200 |
| Questions options and weightage | 200 |
| Sub-domains by domain | 200 |
| Questions by domain | 200 |
| Questions by sub-domain | 200 |
| Questions by domain and sub-domain | 200 |

The previously failing assessment/sub-category endpoints now return HTTP 200.
