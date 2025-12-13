
try:
    import curl_cffi
    print("curl_cffi: installed")
except ImportError as e:
    print(f"curl_cffi: missing ({e})")

try:
    import DrissionPage
    print("DrissionPage: installed")
except ImportError as e:
    print(f"DrissionPage: missing ({e})")
