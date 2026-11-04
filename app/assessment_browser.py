"""Doctor and platform-owner browsing of assessment content, including drafts and scores."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.rows import dict_row

from app.auth.dependencies import bearer_scheme, get_current_user, require_permission
from app.auth.platform import PlatformUser, get_platform_user
from app.db.platform import get_platform_connection

def browser_identity(credentials=Depends(bearer_scheme)):
    # Each authenticator verifies its own token type, signature and account state.
    try:
        return get_platform_user(credentials)
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
    return get_current_user(credentials)


def require_doctor(user=Depends(browser_identity)):
    if isinstance(user, PlatformUser):
        return user
    if user.role != 'DOCTOR':
        raise HTTPException(403, 'Doctor account required.')
    require_permission('ASSESSMENT_ASSIGN')(user)
    return user


# Keep the existing URL for clients; accept verified owner or tenant doctor tokens.
router = APIRouter(prefix='/platform/assessment-browser', tags=['Assessment browser'],
                   dependencies=[Depends(require_doctor)])


def fetch(query, params=(), *, one=False):
    with get_platform_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return cur.fetchone() if one else cur.fetchall()


def require_version(version_id):
    if not fetch('SELECT id FROM assessment_versions WHERE id = %s', (version_id,), one=True):
        raise HTTPException(404, 'Assessment version not found.')


@router.get('/categories')
def categories(limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    return {'items': fetch('''SELECT c.*,
        (SELECT COUNT(*) FROM assessments a WHERE a.category_id = c.id) AS assessment_count
        FROM assessment_categories c ORDER BY c.display_order, c.name, c.id LIMIT %s OFFSET %s''',
        (limit, offset)), 'limit': limit, 'offset': offset}


@router.get('/assessments')
def assessments(category_id: UUID | None = None, code: str | None = None,
                subcategory_id: UUID | None = None,
                limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    return {'items': fetch('''SELECT a.*, c.name AS category_name, sub.name AS subcategory_name
        FROM assessments a LEFT JOIN assessment_categories c ON c.id = a.category_id
        LEFT JOIN assessment_subcategories sub ON sub.id = a.subcategory_id
        WHERE (%s::uuid IS NULL OR a.category_id = %s)
          AND (%s::text IS NULL OR a.code = %s)
          AND (%s::uuid IS NULL OR a.subcategory_id = %s)
        ORDER BY a.name, a.id LIMIT %s OFFSET %s''',
        (category_id, category_id, code, code, subcategory_id, subcategory_id, limit, offset)), 'limit': limit, 'offset': offset}


@router.get('/sub-categories')
def sub_categories(category_id: UUID | None = None,
                   limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    return {'items': fetch('''SELECT sub.*, c.name AS category_name,
        (SELECT COUNT(*) FROM assessments a WHERE a.subcategory_id = sub.id) AS assessment_count
        FROM assessment_subcategories sub JOIN assessment_categories c ON c.id = sub.category_id
        WHERE (%s::uuid IS NULL OR sub.category_id = %s)
        ORDER BY c.display_order, c.id, sub.display_order, sub.name, sub.id LIMIT %s OFFSET %s''',
        (category_id, category_id, limit, offset)), 'limit': limit, 'offset': offset}


@router.get('/assessments/{assessment_id}')
def assessment_detail(assessment_id: UUID):
    item = fetch('''SELECT a.*, c.name AS category_name, sub.name AS subcategory_name FROM assessments a
        LEFT JOIN assessment_categories c ON c.id = a.category_id
        LEFT JOIN assessment_subcategories sub ON sub.id = a.subcategory_id WHERE a.id = %s''',
        (assessment_id,), one=True)
    if item is None:
        raise HTTPException(404, 'Assessment not found.')
    item['versions'] = fetch('''SELECT * FROM assessment_versions WHERE assessment_id = %s
        ORDER BY version_number DESC, id''', (assessment_id,))
    return item


@router.get('/versions/{version_id}')
def version_detail(version_id: UUID):
    item = fetch('''SELECT v.*, a.code AS assessment_code, a.name AS assessment_name,
        (SELECT COUNT(*) FROM assessment_sections s WHERE s.assessment_version_id = v.id) AS domain_count,
        (SELECT COUNT(*) FROM assessment_dimensions d WHERE d.assessment_version_id = v.id) AS sub_domain_count,
        (SELECT COUNT(*) FROM questions q JOIN assessment_sections s ON s.id = q.assessment_section_id
         WHERE s.assessment_version_id = v.id) AS question_count
        FROM assessment_versions v JOIN assessments a ON a.id = v.assessment_id WHERE v.id = %s''',
        (version_id,), one=True)
    if item is None:
        raise HTTPException(404, 'Assessment version not found.')
    item['pricing_history'] = fetch('''SELECT * FROM assessment_pricing
        WHERE assessment_version_id = %s ORDER BY effective_from DESC, id''', (version_id,))
    return item


@router.get('/versions/{version_id}/domains')
def domains(version_id: UUID, limit: int = Query(100, ge=1, le=100),
            offset: int = Query(0, ge=0)):
    require_version(version_id)
    return {'items': fetch('''SELECT s.*,
        (SELECT COUNT(*) FROM questions q WHERE q.assessment_section_id = s.id) AS question_count
        FROM assessment_sections s WHERE s.assessment_version_id = %s
        ORDER BY s.display_order, s.id LIMIT %s OFFSET %s''', (version_id, limit, offset)),
        'limit': limit, 'offset': offset}


def require_domain(version_id, domain_id):
    if domain_id is not None and not fetch('''SELECT id FROM assessment_sections
            WHERE id = %s AND assessment_version_id = %s''', (domain_id, version_id), one=True):
        raise HTTPException(404, 'Domain not found in this version.')


@router.get('/versions/{version_id}/sub-domains')
def sub_domains(version_id: UUID, domain_id: UUID | None = None,
                limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    require_version(version_id)
    require_domain(version_id, domain_id)
    return {'items': fetch('''SELECT d.* FROM assessment_dimensions d
        WHERE d.assessment_version_id = %s AND (%s::uuid IS NULL OR EXISTS (
            SELECT 1 FROM question_option_scores sc
            JOIN question_options o ON o.id = sc.question_option_id
            JOIN questions q ON q.id = o.question_id
            WHERE sc.dimension_id = d.id AND q.assessment_section_id = %s))
        ORDER BY d.display_order, d.id LIMIT %s OFFSET %s''',
        (version_id, domain_id, domain_id, limit, offset)), 'limit': limit, 'offset': offset}


@router.get('/versions/{version_id}/questions')
def questions(version_id: UUID, domain_id: UUID | None = None,
              sub_domain_id: UUID | None = None,
              limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    require_version(version_id)
    require_domain(version_id, domain_id)
    if sub_domain_id is not None and not fetch('''SELECT id FROM assessment_dimensions
            WHERE id = %s AND assessment_version_id = %s''', (sub_domain_id, version_id), one=True):
        raise HTTPException(404, 'Sub-domain not found in this version.')
    items = fetch('''SELECT q.*, s.name AS domain, s.id AS domain_id,
        COALESCE((SELECT jsonb_agg(jsonb_build_object(
            'id', o.id, 'option_number', o.display_order, 'text', o.option_text,
            'value', o.option_value, 'scores', COALESCE((
                SELECT jsonb_agg(jsonb_build_object('sub_domain_id', d.id,
                    'sub_domain', d.name, 'weightage', sc.score) ORDER BY d.display_order, d.id)
                FROM question_option_scores sc JOIN assessment_dimensions d ON d.id = sc.dimension_id
                WHERE sc.question_option_id = o.id
            ), '[]'::jsonb)) ORDER BY o.display_order, o.id)
            FROM question_options o WHERE o.question_id = q.id), '[]'::jsonb) AS options
        FROM questions q JOIN assessment_sections s ON s.id = q.assessment_section_id
        WHERE s.assessment_version_id = %s
          AND (%s::uuid IS NULL OR s.id = %s)
          AND (%s::uuid IS NULL OR EXISTS (
              SELECT 1 FROM question_options o JOIN question_option_scores sc ON sc.question_option_id = o.id
              WHERE o.question_id = q.id AND sc.dimension_id = %s))
        ORDER BY q.display_order, s.display_order, q.id LIMIT %s OFFSET %s''',
        (version_id, domain_id, domain_id, sub_domain_id, sub_domain_id, limit, offset))
    return {'items': items, 'limit': limit, 'offset': offset}
