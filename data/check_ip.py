
import sys
import os

# Add /app to sys.path
sys.path.append('/app')

from core.fetchers.browser_fetcher import BrowserFetcher
from utils.logger import log

def check_ip():
    fetcher = BrowserFetcher(timeout=30)
    url = "http://httpbin.org/ip"
    print(f"Checking IP via BrowserFetcher to {url}...")
    try:
        resp = fetcher.fetch(url)
        print("Response Body:")
        print(resp.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_ip()
