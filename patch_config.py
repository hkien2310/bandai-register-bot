with open("src/config.py", "r", encoding="utf-8") as f:
    code = f.read()

import re
old_str = 'CONFIG_FILE = ROOT_DIR / "config.json"'
new_str = 'import os\nconfig_name = os.environ.get("CONFIG_FILE", "config.json")\nCONFIG_FILE = ROOT_DIR / config_name'

if old_str in code:
    code = code.replace(old_str, new_str)
    with open("src/config.py", "w", encoding="utf-8") as f:
        f.write(code)
    print("Patched config.py")
else:
    print("String not found")
