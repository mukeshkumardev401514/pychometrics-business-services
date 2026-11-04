-- Run these SELECT queries against the platform database.
-- Replace every 'PSY-0134' with the Bio sheet assessment_id.
-- Replace every v.version_number = 1 with the imported version number.
-- Validation-only and dry-run modes do not persist imported data.

-- 1. Assessment and Bio metadata.
SELECT a.*, c.name AS category_name
FROM assessments a
LEFT JOIN assessment_categories c ON c.id = a.category_id
WHERE a.code = 'PSY-0134';

-- 2. All assessment versions.
SELECT v.*
FROM assessment_versions v
JOIN assessments a ON a.id = v.assessment_id
WHERE a.code = 'PSY-0134'
ORDER BY v.version_number;

-- 3. Imported row counts: compare with the workbook.
SELECT
    a.code,
    v.version_number,
    COUNT(DISTINCT s.id) AS domains,
    (SELECT COUNT(*)
     FROM assessment_dimensions d
     WHERE d.assessment_version_id = v.id) AS sub_domains,
    COUNT(DISTINCT q.id) AS questions,
    COUNT(DISTINCT o.id) AS options,
    COUNT(DISTINCT sc.id) AS scores
FROM assessments a
JOIN assessment_versions v ON v.assessment_id = a.id
LEFT JOIN assessment_sections s ON s.assessment_version_id = v.id
LEFT JOIN questions q ON q.assessment_section_id = s.id
LEFT JOIN question_options o ON o.question_id = q.id
LEFT JOIN question_option_scores sc ON sc.question_option_id = o.id
WHERE a.code = 'PSY-0134'
  AND v.version_number = 1
GROUP BY a.code, v.version_number, v.id;

-- 4. Domains and questions.
SELECT
    s.display_order AS domain_order,
    s.name AS domain,
    q.id AS question_id,
    q.display_order AS sr_no,
    q.question_text,
    q.question_type
FROM assessments a
JOIN assessment_versions v ON v.assessment_id = a.id
JOIN assessment_sections s ON s.assessment_version_id = v.id
LEFT JOIN questions q ON q.assessment_section_id = s.id
WHERE a.code = 'PSY-0134'
  AND v.version_number = 1
ORDER BY s.display_order, q.display_order;

-- 5. Questions, options and weightage: compare row by row with Excel.
SELECT
    s.name AS domain,
    d.name AS sub_domain,
    q.display_order AS sr_no,
    q.question_text,
    o.display_order AS option_number,
    o.option_text,
    sc.score AS weightage
FROM assessments a
JOIN assessment_versions v ON v.assessment_id = a.id
JOIN assessment_sections s ON s.assessment_version_id = v.id
JOIN questions q ON q.assessment_section_id = s.id
LEFT JOIN question_options o ON o.question_id = q.id
LEFT JOIN question_option_scores sc ON sc.question_option_id = o.id
LEFT JOIN assessment_dimensions d ON d.id = sc.dimension_id
WHERE a.code = 'PSY-0134'
  AND v.version_number = 1
ORDER BY q.display_order, s.display_order, o.display_order;

-- 6. Sub-domains (the importer stores the domain in description).
SELECT
    d.id,
    d.description AS domain,
    d.name AS sub_domain,
    d.code,
    d.display_order
FROM assessment_dimensions d
JOIN assessment_versions v ON v.id = d.assessment_version_id
JOIN assessments a ON a.id = v.assessment_id
WHERE a.code = 'PSY-0134'
  AND v.version_number = 1
ORDER BY d.display_order;

-- 7. Pricing and percentage split, including history.
SELECT p.*
FROM assessment_pricing p
JOIN assessment_versions v ON v.id = p.assessment_version_id
JOIN assessments a ON a.id = v.assessment_id
WHERE a.code = 'PSY-0134'
  AND v.version_number = 1
ORDER BY p.effective_from DESC;

-- 8. Missing options or scores: expect zero rows after a successful import.
-- Confirm the assessment/version exists with queries 1 and 2 first.
SELECT
    q.display_order AS sr_no,
    q.question_text,
    o.id AS option_id,
    o.option_text,
    CASE
        WHEN o.id IS NULL THEN 'Missing options'
        WHEN sc.id IS NULL THEN 'Missing score'
    END AS issue
FROM assessments a
JOIN assessment_versions v ON v.assessment_id = a.id
JOIN assessment_sections s ON s.assessment_version_id = v.id
JOIN questions q ON q.assessment_section_id = s.id
LEFT JOIN question_options o ON o.question_id = q.id
LEFT JOIN question_option_scores sc ON sc.question_option_id = o.id
WHERE a.code = 'PSY-0134'
  AND v.version_number = 1
  AND (o.id IS NULL OR sc.id IS NULL)
ORDER BY q.display_order;
