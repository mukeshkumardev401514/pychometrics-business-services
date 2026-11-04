import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape
import zipfile

from scripts.import_assessment_xlsx import normalize_questions, read_sheets, run_files


class XlsxImportTests(unittest.TestCase):
    def question(self, **changes):
        return dict(sr_no=1, domain='Performance', sub_domain='Fear', question='Question',
                    option_1='None', weightage_1=0, **changes)

    def test_dynamic_options_zero_and_negative_scores(self):
        row = self.question()
        for i in range(2, 13):
            row[f'option_{i}'] = f'Choice {i}'
            row[f'weightage_{i}'] = -i
        options = normalize_questions([row])[0]['options']
        self.assertEqual(len(options), 12)
        self.assertEqual(options[0], (1, 'None', Decimal(0)))
        self.assertEqual(options[-1][2], Decimal(-12))

    def test_missing_pairs_invalid_scores_and_duplicate_serials(self):
        for changes in ({'option_1': None}, {'weightage_1': None}, {'weightage_1': True},
                        {'weightage_1': 'NaN'}, {'weightage_1': '1.001'},
                        {'weightage_1': 100000000}, {'image': 'photo.png'}, {'sr_no': True},
                        {'option_0': 'bad'}):
            row = self.question()
            row.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize_questions([row])
        with self.assertRaises(ValueError):
            normalize_questions([self.question(), self.question()])

    def test_blank_extra_pairs(self):
        self.assertEqual(len(normalize_questions([self.question(option_5=None, weightage_5=None)])[0]['options']), 1)

    def test_reader_preserves_none_and_ignores_later_sheets(self):
        namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        def sheet(rows):
            xml = ''.join('<row r="%d">%s</row>' % (i, ''.join(
                '<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>' % (chr(65+j), i, escape(value))
                for j, value in enumerate(row))) for i, row in enumerate(rows, 1))
            return f'<worksheet xmlns="{namespace}"><sheetData>{xml}</sheetData></worksheet>'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.xlsx'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('xl/workbook.xml', f'<workbook xmlns="{namespace}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Bio" r:id="r1"/><sheet name="Questions" r:id="r2"/><sheet name="Ignored" r:id="r3"/></sheets></workbook>')
                archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="r1" Target="worksheets/s1.xml"/><Relationship Id="r2" Target="worksheets/s2.xml"/></Relationships>')
                archive.writestr('xl/worksheets/s1.xml', sheet([['assessment_id'], ['PSY-0134']]))
                archive.writestr('xl/worksheets/s2.xml', sheet([['option_1'], ['None']]))
            bio, questions = read_sheets(path)
            self.assertEqual(bio[0]['assessment_id'], 'PSY-0134')
            self.assertEqual(questions[0]['option_1'], 'None')

    def test_folder_failure_policy(self):
        calls = []
        def load(path):
            if path.name == 'bad.xlsx':
                raise ValueError('bad workbook')
            return ({'code': path.stem},), [dict(options=[])]
        paths = list(map(Path, ['one.xlsx', 'bad.xlsx', 'two.xlsx']))
        with patch('scripts.import_assessment_xlsx.load_workbook', side_effect=load):
            self.assertEqual(run_files(paths, lambda item, _: calls.append(item[0]['code'])), 1)
            self.assertEqual(calls, ['one'])
            calls.clear()
            self.assertEqual(run_files(paths, lambda item, _: calls.append(item[0]['code']), True), 1)
            self.assertEqual(calls, ['one', 'two'])


if __name__ == '__main__':
    unittest.main()
