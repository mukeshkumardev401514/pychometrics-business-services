import unittest
from pydantic import ValidationError
from app.resources.models import input_model

class AssessmentMetadataTests(unittest.TestCase):
    def test_normalization_and_optional_metadata(self):
        model = input_model('platform', 'assessments')
        row = model(code='PSY-0132', name='BPAQ', full_name=' BPAQ Full Name ',
                    min_age=0, max_age=130, copyright=float('nan'),
                    charts='Pie Chart, Histogram Chart', domain_charts='y', t_score='n')
        self.assertEqual(row.full_name, 'BPAQ Full Name')
        self.assertEqual(row.charts, ['Pie Chart', 'Histogram Chart'])
        self.assertIsNone(row.copyright)
        self.assertTrue(row.domain_charts)
        self.assertFalse(row.t_score)
        self.assertIsNone(model(code='OLD', name='Existing').min_age)

    def test_invalid_ages_and_charts(self):
        model = input_model('platform', 'assessments', True)
        for values in ({'min_age': -1}, {'max_age': -1}, {'min_age': 30, 'max_age': 20}, {'charts': {'bad': True}}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                model(**values)
        self.assertEqual(model(min_age=10).model_dump(exclude_unset=True), {'min_age': 10})
