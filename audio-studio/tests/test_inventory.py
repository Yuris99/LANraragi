import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('inventory', Path(__file__).resolve().parents[1] / 'inventory.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class InventoryTests(unittest.TestCase):
    def test_candidate_evidence_and_original_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = ['RJ01234567 original/01.wav', 'RJ01234567 translation/01.ass',
                     'RJ01234567 original/RJ123456 other.mp3', 'unknown/track.wma']
            for name in paths:
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b'unchanged')
            report = inventory.scan(root)
            self.assertEqual(report['summary']['files'], 4)
            self.assertEqual(report['summary']['unique_candidate_codes'], 2)
            self.assertEqual(report['summary']['review'], {'candidate': 2, 'multiple_codes': 1, 'missing_code': 1})
            self.assertEqual(report['summary']['categories']['other_media'], 1)
            self.assertEqual(report['errors'], [])
            self.assertTrue(all((root / name).read_bytes() == b'unchanged' for name in paths))

    def test_code_boundaries_and_leading_zeroes(self):
        self.assertEqual(inventory.codes('(rj01234567) RJ123456'), ['RJ01234567', 'RJ123456'])
        self.assertEqual(inventory.codes('XRJ123456 RJ12345 RJ1234567890123'), [])


if __name__ == '__main__':
    unittest.main()
