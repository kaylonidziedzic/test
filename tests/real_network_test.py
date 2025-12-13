
"""
实网代理测试脚本
"""
import sys
import os
import time

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.proxy_manager import proxy_manager
from core.fetchers.cookie_fetcher import CookieFetcher
from utils.logger import log

def test_proxy_connection():
    target_url = "https://nowsecure.in/"
    print(f"--- Creating CookieFetcher ---")
    fetcher = CookieFetcher(retries=0, timeout=15)
    
    print(f"--- Reloading Proxies ---")
    proxy_manager.reload()
    proxies = proxy_manager.get_all()
    print(f"Loaded Proxies: {proxies}")
    
    if not proxies:
        print("Error: No proxies found in data/proxies.txt")
        return

    print(f"--- Starting Request to {target_url} ---")
    try:
        # fetch will internally call proxy_manager.get_proxy()
        resp = fetcher.fetch(target_url)
        print(f"\n[Success]")
        print(f"Status: {resp.status_code}")
        print(f"URL: {resp.url}")
        print(f"Title in text: {'<title>' in resp.text}")
        if resp.status_code == 200:
            print("Response length:", len(resp.text))
    except Exception as e:
        print(f"\n[Failed]")
        print(f"Error: {e}")

if __name__ == "__main__":
    test_proxy_connection()
