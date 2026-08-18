import unittest
from unittest.mock import AsyncMock, call, patch

from server.expense_parser import detect_category, parse_category_correction
from server.main import handle_category_correction


class _FakeChat:
    send_action = AsyncMock()


class _FakeMessage:
    def __init__(self):
        self.chat = _FakeChat()
        self.replies = []

    async def reply_text(self, message, **_kwargs):
        self.replies.append(message)


class _FakeUpdate:
    def __init__(self):
        self.message = _FakeMessage()


class CategoryCorrectionTests(unittest.IsolatedAsyncioTestCase):
    def test_sports_is_a_supported_category_and_correction_target(self):
        self.assertEqual(
            detect_category("I spent RM38 on badminton string"),
            "Sports",
        )
        self.assertEqual(detect_category("I bought mi goreng"), "Food")
        self.assertEqual(
            parse_category_correction("badminton should be sports"),
            {"keywords": ["badminton"], "category": "Sports"},
        )

    def test_parser_splits_comma_separated_items(self):
        correction = parse_category_correction(
            "rice, curry paste should be groceries"
        )

        self.assertEqual(
            correction,
            {"keywords": ["rice", "curry paste"], "category": "Groceries"},
        )

    async def test_handler_saves_each_keyword_and_updates_matching_expense(self):
        update = _FakeUpdate()
        correction = parse_category_correction(
            "rice, curry paste should be groceries"
        )
        expenses = [
            {
                "row_number": 8,
                "sheet_name": "August 2026",
                "description": (
                    "i spent 23.34 on groceries (oil, rice, curry paste, "
                    "potato, carrot, onion, chicken)"
                ),
                "timestamp": "2026-08-15T14:59:00",
            }
        ]

        with (
            patch("server.main.save_learned_category") as save_mapping,
            patch("server.main.get_all_expenses", return_value=expenses),
            patch("server.main.update_expense_category_by_row") as update_row,
        ):
            await handle_category_correction(update, correction)

        self.assertEqual(
            save_mapping.call_args_list,
            [
                call("rice", "Groceries"),
                call("curry paste", "Groceries"),
            ],
        )
        update_row.assert_called_once_with(8, "August 2026", "Groceries")
        self.assertIn("Updated the rice and curry paste expense", update.message.replies[-1])

    async def test_badminton_correction_updates_an_existing_expense(self):
        update = _FakeUpdate()
        correction = parse_category_correction("badminton should be sports")
        expenses = [
            {
                "row_number": 4,
                "sheet_name": "August 2026",
                "description": "i spent RM38 on badminton string (3 Aug)",
                "timestamp": "2026-08-15T14:59:00",
            }
        ]

        with (
            patch("server.main.save_learned_category") as save_mapping,
            patch("server.main.get_all_expenses", return_value=expenses),
            patch("server.main.update_expense_category_by_row") as update_row,
        ):
            await handle_category_correction(update, correction)

        save_mapping.assert_called_once_with("badminton", "Sports")
        update_row.assert_called_once_with(4, "August 2026", "Sports")
        self.assertIn("Updated the badminton expense to Sports", update.message.replies[-1])


if __name__ == "__main__":
    unittest.main()
