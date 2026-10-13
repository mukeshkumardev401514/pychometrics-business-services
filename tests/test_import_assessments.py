import unittest
from decimal import Decimal

from scripts.import_assessments import money, normalize


class AssessmentImportTests(unittest.TestCase):
    def record(self, **changes):
        return dict(assessment_id='PSY-0134', assessment_category='Anxiety',
                    assessment_name='LSAS', min_age=0, max_age=130,
                    assessment_duration=60, **changes)

    def test_source_mapping_and_conversions(self):
        data, category, code, duration, price = normalize(self.record(
            assessment_full_name='Liebowitz Social Anxiety Scale', copyright=' ',
            charts='Pie Chart, Histogram Chart, Line Chart Stacked',
            domain_charts='Y', t_score='N', domain_t_score='N', assessment_cost=0,
        ))
        self.assertEqual(data['code'], 'PSY-0134')
        self.assertEqual(data['name'], 'LSAS')
        self.assertEqual(data['full_name'], 'Liebowitz Social Anxiety Scale')
        self.assertEqual(data['charts'], ['Pie Chart', 'Histogram Chart', 'Line Chart Stacked'])
        self.assertIsNone(data['copyright'])
        self.assertTrue(data['domain_charts'])
        self.assertFalse(data['t_score'])
        self.assertEqual((category, code, duration, price), ('Anxiety', 'ANXIETY', 60, Decimal(0)))

    def test_missing_and_null_are_distinct(self):
        self.assertNotIn('description', normalize(self.record())[0])
        self.assertIsNone(normalize(self.record(description=None))[0]['description'])
        self.assertIsNone(normalize(self.record(assessment_cost=None))[4])

    def test_invalid_ages_duration_and_fields(self):
        for changes in ({'min_age': -1}, {'max_age': -1}, {'min_age': 131},
                        {'min_age': True}, {'assessment_duration': 0},
                        {'assessment_duration': '60'}, {'t_score': 'maybe'},
                        {'charts': {}}, {'assessment_cost': -1}, {'typo': 'value'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                record = self.record()
                record.update(changes)
                normalize(record)

    def test_numeric_precision_and_bounds(self):
        for value in ('NaN', 'Infinity', '-1', '100.001', '101', True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                money(value, 'percentage', Decimal(100))
        self.assertEqual(money('70.25', 'percentage', Decimal(100)), Decimal('70.25'))


if __name__ == '__main__':
    unittest.main()
