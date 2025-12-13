import requests
import json
import time

API_KEY = "admin-change-this"
BASE_URL = "http://localhost:8000"

def test_rules():
    # 1. Create Rule
    print("Creating Rule...")
    payload = {
        "name": "Test Rule",
        "target_url": "http://httpbin.org/html",
        "method": "GET",
        "mode": "cookie",
        "selectors": {
            "title": "h1"
        }
    }
    headers = {"X-API-KEY": API_KEY, "Content-Type": "application/json"}
    
    try:
        resp = requests.post(f"{BASE_URL}/v1/rules", json=payload, headers=headers)
        if resp.status_code != 200:
            print(f"Failed to create rule: {resp.text}")
            return
        
        data = resp.json()
        rule_id = data["id"]
        permlink = data["permlink"]
        print(f"Rule Created: {rule_id}, Link: {permlink}")
        
        # 2. List Rules
        print("Listing Rules...")
        resp = requests.get(f"{BASE_URL}/v1/rules", headers=headers)
        rules = resp.json().get("rules", [])
        found = any(r["id"] == rule_id for r in rules)
        print(f"Rule found in list: {found}")
        
        # 3. Execute Rule
        print("Executing Rule...")
        run_url = f"{BASE_URL}{permlink}"
        resp = requests.get(run_url)
        print(f"Execution Status: {resp.status_code}")
        print(f"Execution Result: {json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_rules()
