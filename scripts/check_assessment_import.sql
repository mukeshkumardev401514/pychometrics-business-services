-- Import ke baad PLATFORM database mein ye file run karein.
-- Neeche assessment_code aur version_number set karein.
-- Summary ki counts Excel se match karein; issues array empty honi chahiye.
-- Ye query data change nahi karti.

WITH
input AS (
    SELECT 'PSY-0134'::text AS assessment_code, 1::integer AS version_number
),
target AS (
    SELECT a.id AS assessment_id, v.id AS version_id,
           a.code, a.name, a.category_id, a.subcategory_id, v.version_number,
           v.status, v.duration_minutes
    FROM input i
    JOIN assessments a ON a.code = i.assessment_code
    LEFT JOIN assessment_versions v
      ON v.assessment_id = a.id AND v.version_number = i.version_number
),
sections AS (
    SELECT s.*
    FROM assessment_sections s
    JOIN target t ON t.version_id = s.assessment_version_id
),
dimensions AS (
    SELECT d.*
    FROM assessment_dimensions d
    JOIN target t ON t.version_id = d.assessment_version_id
),
question_rows AS (
    SELECT q.*, s.name AS domain, s.display_order AS domain_order
    FROM questions q
    JOIN sections s ON s.id = q.assessment_section_id
),
options AS (
    SELECT o.*
    FROM question_options o
    JOIN question_rows q ON q.id = o.question_id
),
scores AS (
    SELECT sc.*
    FROM question_option_scores sc
    JOIN options o ON o.id = sc.question_option_id
),
issues AS (
    SELECT 'Assessment not found'::text AS issue, NULL::text AS detail
    WHERE NOT EXISTS (SELECT 1 FROM target)
    UNION ALL
    SELECT 'Version not found', NULL
    FROM target WHERE version_id IS NULL
    UNION ALL
    SELECT 'No questions found', NULL
    WHERE EXISTS (SELECT 1 FROM target WHERE version_id IS NOT NULL)
      AND NOT EXISTS (SELECT 1 FROM question_rows)
    UNION ALL
    SELECT 'Question has no options', 'sr_no=' || q.display_order
    FROM question_rows q
    WHERE NOT EXISTS (SELECT 1 FROM options o WHERE o.question_id = q.id)
    UNION ALL
    SELECT 'Option must have exactly one score',
           'sr_no=' || q.display_order || ', option=' || o.display_order
    FROM options o
    JOIN question_rows q ON q.id = o.question_id
    WHERE (SELECT COUNT(*) FROM scores sc WHERE sc.question_option_id = o.id) <> 1
    UNION ALL
    SELECT 'Score dimension belongs to another version',
           'sr_no=' || q.display_order || ', option=' || o.display_order
    FROM scores sc
    JOIN options o ON o.id = sc.question_option_id
    JOIN question_rows q ON q.id = o.question_id
    WHERE NOT EXISTS (SELECT 1 FROM dimensions d WHERE d.id = sc.dimension_id)
)
SELECT
    i.assessment_code,
    i.version_number,
    CASE WHEN EXISTS (SELECT 1 FROM issues)
         THEN 'CHECK ISSUES'
         ELSE 'Structure OK - compare values and counts with Excel'
    END AS check_result,
    (SELECT to_jsonb(t) FROM target t) AS assessment_version,
    (SELECT to_jsonb(a) FROM assessments a
     JOIN target t ON t.assessment_id = a.id) AS bio_metadata,
    (SELECT c.name FROM assessment_categories c
     JOIN target t ON t.category_id = c.id) AS category,
    (SELECT sub.name FROM assessment_subcategories sub
     JOIN target t ON t.subcategory_id = sub.id) AS sub_category,
    jsonb_build_object(
        'domains', (SELECT COUNT(*) FROM sections),
        'sub_domains', (SELECT COUNT(*) FROM dimensions),
        'questions', (SELECT COUNT(*) FROM question_rows),
        'options', (SELECT COUNT(*) FROM options),
        'scores', (SELECT COUNT(*) FROM scores)
    ) AS counts,
    COALESCE((SELECT jsonb_agg(to_jsonb(e) ORDER BY e.issue, e.detail)
              FROM issues e), '[]'::jsonb) AS issues,
    COALESCE((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.effective_from DESC)
              FROM assessment_pricing p
              JOIN target t ON t.version_id = p.assessment_version_id),
             '[]'::jsonb) AS pricing_history,
    COALESCE((SELECT jsonb_agg(to_jsonb(d) ORDER BY d.display_order)
              FROM dimensions d), '[]'::jsonb) AS sub_domains,
    COALESCE((
        SELECT jsonb_agg(
            jsonb_build_object(
                'domain', q.domain,
                'sr_no', q.display_order,
                'question', q.question_text,
                'question_type', q.question_type,
                'option_number', o.display_order,
                'option', o.option_text,
                'sub_domain', d.name,
                'weightage', sc.score
            ) ORDER BY q.display_order, q.domain_order, o.display_order, d.display_order
        )
        FROM question_rows q
        LEFT JOIN options o ON o.question_id = q.id
        LEFT JOIN scores sc ON sc.question_option_id = o.id
        LEFT JOIN assessment_dimensions d ON d.id = sc.dimension_id
    ), '[]'::jsonb) AS questions_options_scores
FROM input i;
