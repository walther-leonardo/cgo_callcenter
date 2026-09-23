from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

INBOX_DIR = PROJECT_ROOT / "inbox"
DATA_DIR = PROJECT_ROOT / "data"

DATABASE_PATH = DATA_DIR / "callcenter.db"

CLEARMECHANIC_FILE = INBOX_DIR / "clearmechanic.xlsx"