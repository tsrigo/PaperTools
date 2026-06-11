import unittest

from src.utils.exceptions import ValidationError
from src.utils.validation import (
    validate_date_inputs,
    validate_non_negative_int,
    validate_positive_float,
    validate_positive_int,
)


class ValidationTests(unittest.TestCase):
    def test_validate_date_inputs_accepts_single_date(self):
        date, start, end = validate_date_inputs(date="2026-04-22")
        self.assertEqual((date, start, end), ("2026-04-22", None, None))

    def test_validate_date_inputs_accepts_range(self):
        date, start, end = validate_date_inputs(
            start_date="2026-04-20", end_date="2026-04-22"
        )
        self.assertEqual((date, start, end), (None, "2026-04-20", "2026-04-22"))

    def test_validate_date_inputs_rejects_mixed_modes(self):
        with self.assertRaises(ValidationError):
            validate_date_inputs(
                date="2026-04-22", start_date="2026-04-20", end_date="2026-04-22"
            )

    def test_validate_date_inputs_rejects_reversed_range(self):
        with self.assertRaises(ValidationError):
            validate_date_inputs(start_date="2026-04-23", end_date="2026-04-22")

    def test_validate_positive_int(self):
        self.assertEqual(validate_positive_int(3, "--workers"), 3)
        with self.assertRaises(ValidationError):
            validate_positive_int(0, "--workers")

    def test_validate_non_negative_int(self):
        self.assertEqual(validate_non_negative_int(0, "--max-papers"), 0)
        with self.assertRaises(ValidationError):
            validate_non_negative_int(-1, "--max-papers")

    def test_validate_positive_float(self):
        self.assertEqual(validate_positive_float(0.5, "--delay"), 0.5)
        self.assertEqual(validate_positive_float(0.0, "--delay", allow_zero=True), 0.0)
        with self.assertRaises(ValidationError):
            validate_positive_float(0.0, "--delay")


if __name__ == "__main__":
    unittest.main()
