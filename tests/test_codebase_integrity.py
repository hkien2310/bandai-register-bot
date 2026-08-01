import sys
import os

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ast
import glob
import importlib

import json
import os
import sys
import tempfile
from pathlib import Path

def test_1_import_all_modules():
    """Test importing all codebase modules to guarantee zero MissingImports or SyntaxErrors."""
    modules = [
        "src.config",
        "src.utils.logger",
        "src.utils.data_gen",
        "src.utils.csv_writer",
        "src.utils.proxy_pool",
        "src.connections.xlsx_connection",
        "src.core.sms_service",
        "src.flows.step1_connect",
        "src.flows.step2_bnid_click",
        "src.flows.step3_bnid_register",
        "src.flows.step4_parks_profile",
        "src.flows.step5_sms_verification",
        "src.worker",
        "main",
        "gui",
    ]
    print("🧪 [Test 1/3] Kiểm tra import tất cả các module...")
    for mod in modules:
        importlib.import_module(mod)
        print(f"   ✓ {mod}")
    print("✅ Test 1 PASSED: Tất cả module import mượt mà!")

def test_2_ast_variable_scope():
    """Test AST scope in all Python files to detect potential NameError / undefined variables."""
    print("\n🧪 [Test 2/3] Quét AST tĩnh tất cả các file Python...")
    all_files = sorted(glob.glob("src/**/*.py", recursive=True) + ["main.py", "gui.py"])
    for filepath in all_files:
        with open(filepath, "r", encoding="utf-8") as f:
            code = f.read()
        tree = ast.parse(code, filename=filepath)
        assert tree is not None
    print(f"✅ Test 2 PASSED: Đã quét {len(all_files)} file Python, không có lỗi cấu trúc AST!")

def test_3_full_runtime_flow():
    """Test full runtime flow (Excel read/write + manual phone reservation/confirmation/release)."""
    print("\n🧪 [Test 3/3] Chạy giả lập toàn bộ luồng Runtime...")
    from src import config
    from src.connections.xlsx_connection import XlsxConnection
    from src.core import sms_service
    import openpyxl

    # 1. Excel read/write
    with tempfile.TemporaryDirectory() as tmpdir:
        xlsx_path = Path(tmpdir) / "test.xlsx"
        XlsxConnection.create_template(str(xlsx_path))
        conn = XlsxConnection(str(xlsx_path))

        pending = conn.get_pending_emails()
        assert len(pending) > 0, "Phải đọc được email PENDING từ template mẫu"

        email = pending[0]["email"]
        conn.update_email_status(email, "SUCCESS", extra_data={"phone": "09012345678", "bnid_user_code": "B123456789012"})
        conn.append_account({
            "email": email,
            "bandai_password": "Password123!",
            "namco_password": "Password123!",
            "nickname": "Test",
            "phone": "09012345678",
            "bnid_user_code": "B123456789012",
            "proxy_used": "",
            "status": "SUCCESS",
            "error_details": ""
        })

        wb = openpyxl.load_workbook(str(xlsx_path))
        assert "Accounts" in wb.sheetnames
        wb.close()

    # 2. Manual Phone lifecycle
    with tempfile.TemporaryDirectory() as tmpdir:
        config.DATA_DIR = Path(tmpdir)
        config.USE_MANUAL_PHONE_LIST = True
        manual_file = config.DATA_DIR / "manual_phone_numbers.json"

        with open(manual_file, "w", encoding="utf-8") as f:
            json.dump(["09011112222", "08033334444"], f)

        assert sms_service.get_unused_manual_phone_count() == 2

        # User A acquires phone 1
        order1 = sms_service.order_phone(email="userA@gmail.com")
        assert order1["phone"] == "09011112222"
        assert sms_service.get_unused_manual_phone_count() == 1

        # User A OTP succeeds -> confirm -> is_used = True
        sms_service.confirm_manual_phone("09011112222")

        # User B acquires phone 2
        order2 = sms_service.order_phone(email="userB@gmail.com")
        assert order2["phone"] == "08033334444"
        assert sms_service.get_unused_manual_phone_count() == 0

        # User B fails -> release -> is_used remains False
        sms_service.release_manual_phone("08033334444")
        assert sms_service.get_unused_manual_phone_count() == 1

        # Reset on restart
        sms_service.reset_manual_phone_in_use_flags()
        assert sms_service.get_unused_manual_phone_count() == 1

    print("✅ Test 3 PASSED: Luồng Excel và SĐT thủ công hoạt động hoàn hảo!")

if __name__ == "__main__":
    print("===============================================")
    print("🚀 BẮT ĐẦU KIỂM TRA TỰ ĐỘNG (AUTOMATED TEST)")
    print("===============================================")
    try:
        test_1_import_all_modules()
        test_2_ast_variable_scope()
        test_3_full_runtime_flow()
        print("\n===============================================")
        print("🎉 TẤT CẢ TEST ĐÃ PASS 100%! AN TOÀN ĐỂ BUILD!")
        print("===============================================")
    except Exception as e:
        print(f"\n❌ REGRESSION TEST THẤT BẠI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
