import unittest

from server.sheets import _build_expense_summary, _column_letter


class SheetHelperTests(unittest.TestCase):
    def test_column_labels_support_multi_letter_columns(self):
        self.assertEqual(_column_letter(1), "A")
        self.assertEqual(_column_letter(26), "Z")
        self.assertEqual(_column_letter(27), "AA")

    def test_summary_format_is_shared_for_sheet_summary_views(self):
        summary = _build_expense_summary(
            [
                {"amount": "2", "category": "Food"},
                {"amount": "3", "category": "Groceries"},
            ],
            heading="Expense Summary - August 2026",
            period_label="August 2026",
        )

        self.assertEqual(
            summary,
            "*Expense Summary - August 2026*\n\n"
            "• Groceries: *RM3.00* (60%)\n"
            "• Food: *RM2.00* (40%)\n\n"
            "*Total: RM5.00*\n"
            "2 expense(s) recorded",
        )


if __name__ == "__main__":
    unittest.main()
