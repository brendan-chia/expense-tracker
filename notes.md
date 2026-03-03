Problem 
1. I have an issue where my expense_parser.py is incorrectly parsing 'eighty cents' as RM80.00 instead of RM0.80.

2. 
ori: try:
    from sheets import get_client, ensure_sheet, SHEET_NAME

new: try:
        from server.sheets import get_client, ensure_sheet, SHEET_NAME

The code snippet you provided is a robust import handler designed to solve a very specific problem that happens when projects are moved between local development (your laptop) and cloud hosting like Vercel.

In your local project, your files are inside a server/ folder. Sometimes Python thinks the "root" is the top folder, and other times it thinks it is inside server/. This solution uses nested try...except blocks to find sheets.py no matter where Python is looking.
