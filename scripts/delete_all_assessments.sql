-- Run against the PLATFORM database before re-importing XLSX files.
-- Deletes ALL assessments, not just one assessment code.
-- ON DELETE CASCADE also deletes their versions, sections, dimensions,
-- questions, options, option scores, scoring rules and pricing history.
-- Deletes ALL assessment categories after deleting assessments.
-- Tenant databases are separate and are not cleaned by this script.

BEGIN;

DELETE FROM assessments;
DELETE FROM assessment_subcategories;
DELETE FROM assessment_categories;

-- All counts below should be zero after deleting all assessments.
SELECT 'assessments' AS table_name, COUNT(*) AS remaining FROM assessments
UNION ALL
SELECT 'assessment_categories', COUNT(*) FROM assessment_categories
UNION ALL
SELECT 'assessment_subcategories', COUNT(*) FROM assessment_subcategories
UNION ALL
SELECT 'assessment_versions', COUNT(*) FROM assessment_versions
UNION ALL
SELECT 'assessment_sections', COUNT(*) FROM assessment_sections
UNION ALL
SELECT 'assessment_dimensions', COUNT(*) FROM assessment_dimensions
UNION ALL
SELECT 'questions', COUNT(*) FROM questions
UNION ALL
SELECT 'question_options', COUNT(*) FROM question_options
UNION ALL
SELECT 'question_option_scores', COUNT(*) FROM question_option_scores
UNION ALL
SELECT 'scoring_rules', COUNT(*) FROM scoring_rules
UNION ALL
SELECT 'assessment_pricing', COUNT(*) FROM assessment_pricing;

COMMIT;
