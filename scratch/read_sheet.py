import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.google_sheets_manager import GoogleSheetsManager

def main():
    manager = GoogleSheetsManager()
    if not manager.is_connected():
        print("Failed to connect to Google Sheets.")
        return

    try:
        print("--- Mails Sheet Headers ---")
        print(manager.mails_sheet.row_values(1))
    except Exception as e:
        print(f"Error reading Mails sheet: {e}")

    try:
        print("--- Proxies Sheet Headers ---")
        print(manager.proxies_sheet.row_values(1))
    except Exception as e:
        print(f"Error reading Proxies sheet: {e}")

    try:
        print("--- Accounts Sheet Headers ---")
        print(manager.accounts_sheet.row_values(1))
    except Exception as e:
        print(f"Error reading Accounts sheet: {e}")

if __name__ == "__main__":
    main()
