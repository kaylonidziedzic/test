
import urllib.request
import urllib.parse
import json
import time

def test_proxy_api():
    url = "http://localhost:8000/v1/proxy"
    # Target URL to fetch via the gateway
    payload = {
        "url": "https://nowsecure.in/", 
        "mode": "cookie"
    }
    data = json.dumps(payload).encode('utf-8')
    
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header('Content-Type', 'application/json')
    # Default API Key from docker-compose
    req.add_header('X-API-KEY', 'change_me_please')

    print(f"Sending request to {url}...")
    try:
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=30) as response:
            resp_body = response.read().decode('utf-8')
            resp_json = json.loads(resp_body)
            duration = time.time() - start_time
            
            print(f"✅ Success! Duration: {duration:.2f}s")
            print(f"Status Code: {response.getcode()}")
            print(f"Response Body Preview: {resp_body[:200]}...")
            
            if "status" in resp_json:
                print(f"Gateway Status: {resp_json['status']}")
            
            return True
            
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error: {e.code} {e.reason}")
        print(e.read().decode('utf-8'))
    except urllib.error.URLError as e:
        print(f"❌ Connection Error: {e.reason}")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")

    return False

if __name__ == "__main__":
    # Wait a bit for services to stabilize
    print("Waiting 5s for services to start...")
    time.sleep(5)
    test_proxy_api()
