"""Published assessment versions available to authenticated assigning doctors."""
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.rows import dict_row
from app.auth.dependencies import CurrentUser, require_permission
from app.db.platform import get_platform_connection

router = APIRouter()


@router.get('/assessment-catalog', tags=['Assessments'])
def assessment_catalog(limit: int = Query(100, ge=1, le=100),
                       offset: int = Query(0, ge=0),
                       user: CurrentUser = Depends(require_permission('ASSESSMENT_ASSIGN'))):
    if user.role != 'DOCTOR':
        raise HTTPException(403, 'Doctor account required.')
    with get_platform_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, name, display_order FROM assessment_categories WHERE status = 'ACTIVE' ORDER BY display_order, name, id")
            categories = cur.fetchall()
            cur.execute('''SELECT a.id AS assessment_id, a.name, a.description,
                                  v.id AS assessment_version_id, v.version_number, v.duration_minutes,
                                  c.id AS category_id, c.name AS category_name,
                                  c.display_order AS category_order,
                                  pricing.price::text AS price, pricing.currency,
                                  (SELECT COUNT(*) FROM questions q
                                   JOIN assessment_sections section ON section.id = q.assessment_section_id
                                   WHERE section.assessment_version_id = v.id) AS total_questions
                           FROM assessments a JOIN assessment_versions v ON v.assessment_id = a.id
                           LEFT JOIN assessment_categories c ON c.id = a.category_id
                           LEFT JOIN LATERAL (
                               SELECT price, currency FROM assessment_pricing
                               WHERE assessment_version_id = v.id AND status = 'ACTIVE'
                                 AND effective_from <= NOW()
                                 AND (effective_to IS NULL OR effective_to > NOW())
                               ORDER BY effective_from DESC, created_at DESC, id DESC LIMIT 1
                           ) pricing ON TRUE
                           WHERE a.status = 'PUBLISHED' AND v.status = 'PUBLISHED'
                           ORDER BY a.name, a.id, v.version_number DESC, v.id
                           LIMIT %s OFFSET %s''', (limit, offset))
            return {'categories': categories, 'items': cur.fetchall(), 'limit': limit, 'offset': offset}
