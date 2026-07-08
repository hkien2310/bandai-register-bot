import json
from urllib.parse import unquote, urlparse

def analyze_logs():
    with open("scratch/network_log.json", "r", encoding="utf-8") as f:
        logs = json.load(f)

    print(f"Total logs: {len(logs)}")
    interesting_logs = []
    
    for entry in logs:
        url = entry.get("url", "")
        method = entry.get("method", "")
        parsed = urlparse(url)
        host = parsed.netloc
        
        # MUST exactly be the target domain
        if host != "parks2.bandainamco-am.co.jp":
            continue
            
        # Ignore obvious assets
        if any(url.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".css", ".js", ".woff2", ".gif", ".svg"]):
            continue

        is_post = method == "POST"
        is_api = "api" in parsed.path.lower() or "cart" in parsed.path.lower() or "add" in parsed.path.lower() or "product" in parsed.path.lower() or "item" in parsed.path.lower()
        
        # We want to see all POST requests or any API/cart related GET
        if is_post or is_api or True:  # Let's just print ALL non-asset requests to this domain to be safe
            resp_keys = []
            if entry.get("response_json"):
                if isinstance(entry["response_json"], dict):
                    resp_keys = list(entry["response_json"].keys())
                elif isinstance(entry["response_json"], list):
                    resp_keys = ["list_of_items"]
                    
            interesting_logs.append({
                "method": method,
                "url": url,
                "post_data": entry.get("post_data"),
                "status": entry.get("status"),
                "response_keys": resp_keys
            })

    print(f"Found {len(interesting_logs)} interesting requests to bandainamco:")
    for log in interesting_logs:
        print(f"[{log['method']}] {unquote(log['url'])}")
        if log['post_data']:
            pd = str(log['post_data'])
            if len(pd) > 500: pd = pd[:500] + "..."
            print(f"   Payload: {unquote(pd)}")
        if log['response_keys']:
            print(f"   Response Keys: {log['response_keys']}")
        print("-" * 80)

if __name__ == "__main__":
    analyze_logs()
