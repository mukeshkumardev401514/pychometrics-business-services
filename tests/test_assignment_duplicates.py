import unittest
from unittest.mock import MagicMock
from uuid import uuid4
from fastapi import HTTPException
from app.resources.service import ensure_single_pending_assignment

class AssignmentDuplicateTests(unittest.TestCase):
    def test_pending_test_rejected_before_insert(self):
        cur = MagicMock()
        cur.fetchone.return_value = {'id': uuid4()}
        for status in ('PENDING_PAYMENT', 'ASSIGNED', 'IN_PROGRESS'):
            with self.subTest(status=status), self.assertRaises(HTTPException) as error:
                ensure_single_pending_assignment(cur, dict(patient_id=uuid4(), assessment_id=uuid4(), assignment_status=status))
            self.assertEqual(error.exception.status_code, 409)
        self.assertIn('pg_advisory_xact_lock', cur.execute.call_args_list[0].args[0])

    def test_no_duplicate_and_existing_row_excluded(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        row = dict(id=uuid4(), patient_id=uuid4(), assessment_id=uuid4())
        ensure_single_pending_assignment(cur, row)
        self.assertEqual(cur.execute.call_args.args[1], (row['patient_id'], row['assessment_id'], row['id'], row['id']))

    def test_cancellation_is_allowed(self):
        cur = MagicMock()
        ensure_single_pending_assignment(cur, {'assignment_status': 'CANCELLED'})
        cur.execute.assert_not_called()
