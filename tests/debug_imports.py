
import sys
import os
import traceback

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("Python executable:", sys.executable)
print("Python path:", sys.path)

try:
    print("Importing utils.logger...")
    from utils.logger import log
    print("✅ utils.logger imported")
except ImportError:
    traceback.print_exc()

try:
    print("Importing services.proxy_manager...")
    from services.proxy_manager import proxy_manager
    print("✅ services.proxy_manager imported")
except ImportError:
    traceback.print_exc()

try:
    print("Importing core.fetchers.cookie_fetcher...")
    from core.fetchers.cookie_fetcher import CookieFetcher
    print("✅ core.fetchers.cookie_fetcher imported")
except ImportError:
    traceback.print_exc()

print("Done debugging imports.")
