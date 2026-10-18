import os
import sys

APP_NAME = "AlfaDrop"
APP_SUBTITLE = "Store File Deployer"

# sys.argv[0] (not __file__) so this resolves to the folder the .exe lives in,
# even when frozen by PyInstaller with --onefile.
BASE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
RESOURCE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

STORES_FILE = os.path.join(BASE_DIR, "stores.txt")
KNOWN_HOSTS_FILE = os.path.join(BASE_DIR, "known_hosts.txt")
LOG_FILE = os.path.join(BASE_DIR, "alfadrop.log")
LOG_MAX_BYTES = 2 * 1024 * 1024          # rotated to alfadrop.log.old at this size

DEFAULT_REMOTE_DIR = r"C:\AlfaDrop"
DEFAULT_WORKERS = 10                     # PCs deployed to at the same time
MAX_WORKERS = 50

CONNECT_TIMEOUT_SEC = 8
UPLOAD_MAX_ATTEMPTS = 3
UPLOAD_RETRY_DELAY_SEC = 1.5
PROGRESS_UPDATE_SEC = 0.5

LOG_PANEL_MAX_LINES = 3000               # the log file keeps the full history