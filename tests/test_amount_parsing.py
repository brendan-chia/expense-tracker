import unittest

from server.expense_parser import extract_amount


class AmountParsingTests(unittest.TestCase):
    def test_cents_only_amounts_are_converted_to_ringgit(self):
        cases = {
            "eighty cents": 0.80,
            "I spent eighty cents on candy": 0.80,
            "80 cents": 0.80,
            "eighty sen": 0.80,
        }

        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(extract_amount(text), expected)

    def test_ringgit_and_cents_forms_still_work(self):
        cases = {
            "fifteen ringgit thirty-two cents": 15.32,
            "15 ringgit 32 cents": 15.32,
            "fifteen ringgit 32 cents": 15.32,
            "one hundred and twenty cents": 1.20,
        }

        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(extract_amount(text), expected)


if __name__ == "__main__":
    unittest.main()
