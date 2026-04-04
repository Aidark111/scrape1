import requests

CLOUD_RUN_URL = "https://hello-912470754071.europe-west1.run.app"

def debug_cloud_run():
    url = f"{CLOUD_RUN_URL}/api/generate"
    payload = {
        "model": "llama3", 
        "prompt": "Hello",
        "stream": False
    }
    
    print(f"Sending POST request to {url}...\n")
    
    try:
        # Send the request
        response = requests.post(url, json=payload)
        
        # Print the raw status and text, no matter what it is
        print(f"Status Code: {response.status_code}")
        print("Raw Response Output:")
        print("-" * 50)
        # We slice to 500 characters just in case it spits out a massive HTML page
        print(response.text[:500]) 
        print("-" * 50)
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    debug_cloud_run()