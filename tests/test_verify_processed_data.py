import gzip
import tempfile
import unittest
from pathlib import Path

from scripts.verify_processed_data import count_gzip_csv_data_lines


class VerifyProcessedDataTests(unittest.TestCase):
    def test_counts_gzip_csv_rows_and_reads_to_eof(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unmatched.csv.gz"
            with gzip.open(path, "wb") as stream:
                stream.write("learner_id,problem_id\nU_1,Pm_1\nU_2,Pm_2".encode())

            self.assertEqual(count_gzip_csv_data_lines(path, chunk_size=5), 2)


if __name__ == "__main__":
    unittest.main()
