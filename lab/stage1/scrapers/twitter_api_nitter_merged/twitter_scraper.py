"""
Option 4: Google Custom Search with OAuth (client_secret.json)
Search site:twitter.com "query" to find tweet URLs
"""

import os
import re
import json
import time
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from pathlib import Path

# Google OAuth libraries
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ============================================================
# SETUP INSTRUCTIONS
# ============================================================
# 1. Go to: https://console.cloud.google.com/
# 2. Create project → Enable "Custom Search API"
# 3. Go to "Credentials" → Create OAuth 2.0 Client ID
#    - Application type: Desktop app
#    - Download the JSON → rename to "client_secret.json"
# 4. Go to: https://cse.google.com/cse/
#    - Create search engine → note the Search Engine ID (cx)
#    - In settings, enable "Search the entire web"
# ============================================================

# Configuration
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"  # Stores your auth token after first login
SCOPES = ["https://www.googleapis.com/auth/cse"]  # Custom Search scope

# Your Custom Search Engine ID (get from cse.google.com)
SEARCH_ENGINE_ID = "42139bfb92cab4914"  # e.g., "a1b2c3d4e5f6g7h8i"


@dataclass
class TweetResult:
    url: str
    title: str
    snippet: str
    username: Optional[str] = None
    tweet_id: Optional[str] = None
    discovered_at: str = ""
    
    def __post_init__(self):
        if not self.discovered_at:
            self.discovered_at = datetime.now().isoformat()


def get_google_credentials():
    """
    Handle OAuth flow and return valid credentials.
    First run opens browser for authorization.
    Subsequent runs use saved token.
    """
    creds = None
    
    # Check for existing token
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # If no valid credentials, do OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired token
            creds.refresh(Request())
        else:
            # Run full OAuth flow (opens browser)
            if not os.path.exists(CLIENT_SECRET_FILE):
                raise FileNotFoundError(
                    f"Missing {CLIENT_SECRET_FILE}!\n"
                    "Download from Google Cloud Console → Credentials → OAuth 2.0 Client IDs"
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, 
                SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        # Save token for future runs
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
        print(f"✅ Credentials saved to {TOKEN_FILE}")
    
    return creds


def build_search_service():
    """Build the Custom Search API service."""
    creds = get_google_credentials()
    service = build('customsearch', 'v1', credentials=creds)
    return service


def parse_tweet_url(url: str) -> Optional[dict]:
    """Extract username and tweet ID from Twitter/X URL."""
    patterns = [
        r'(?:twitter\.com|x\.com)/(\w+)/status/(\d+)',
        r'mobile\.twitter\.com/(\w+)/status/(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return {
                'username': match.group(1),
                'tweet_id': match.group(2)
            }
    return None


def google_search_tweets(
    query: str,
    max_results: int = 100,
    search_engine_id: str = SEARCH_ENGINE_ID
) -> list[TweetResult]:
    """
    Search Google for tweets matching a query using OAuth.
    
    Args:
        query: Search terms
        max_results: Maximum tweets to find (100/day free tier)
        search_engine_id: Your CSE ID from cse.google.com
    
    Returns:
        List of TweetResult objects
    """
    
    service = build_search_service()
    results = []
    
    # Google CSE: 10 results per page, max 100 total
    num_pages = min(max_results // 10, 10)
    
    # Build query to search Twitter/X
    full_query = f'site:twitter.com OR site:x.com "{query}"'
    
    for page in range(num_pages):
        start_index = page * 10 + 1
        
        try:
            # Execute search
            response = service.cse().list(
                q=full_query,
                cx=search_engine_id,
                start=start_index,
                num=10
            ).execute()
            
            if 'items' not in response:
                print(f"No more results at page {page + 1}")
                break
            
            for item in response['items']:
                url = item.get('link', '')
                tweet_info = parse_tweet_url(url)
                
                if tweet_info:
                    result = TweetResult(
                        url=url,
                        title=item.get('title', ''),
                        snippet=item.get('snippet', ''),
                        username=tweet_info.get('username'),
                        tweet_id=tweet_info.get('tweet_id')
                    )
                    results.append(result)
            
            print(f"Page {page + 1}: Found {len(response['items'])} results")
            time.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            print(f"Error on page {page + 1}: {e}")
            break
    
    return results


def search_multiple_queries(
    queries: list[str], 
    results_per_query: int = 20
) -> list[TweetResult]:
    """Search for tweets across multiple queries, deduplicated."""
    
    all_results = []
    seen_tweet_ids = set()
    
    for query in queries:
        print(f"\n🔍 Searching: {query}")
        results = google_search_tweets(query, max_results=results_per_query)
        
        for result in results:
            if result.tweet_id and result.tweet_id not in seen_tweet_ids:
                seen_tweet_ids.add(result.tweet_id)
                all_results.append(result)
        
        print(f"   Unique total: {len(all_results)}")
        time.sleep(1)
    
    return all_results


def save_results(results: list[TweetResult], filename: str = "tweets.json"):
    """Save results to JSON file."""
    with open(filename, 'w') as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    print(f"📁 Saved {len(results)} tweets to {filename}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    
    print("=" * 60)
    print("Google Custom Search → Twitter (OAuth)")
    print("=" * 60)
    
    # Check for client secret
    if not os.path.exists(CLIENT_SECRET_FILE):
        print(f"""
❌ Missing {CLIENT_SECRET_FILE}!

Setup steps:
1. Go to https://console.cloud.google.com/
2. Create/select project
3. Enable "Custom Search API"
4. Go to Credentials → Create OAuth 2.0 Client ID
5. Application type: Desktop app
6. Download JSON → rename to {CLIENT_SECRET_FILE}
7. Place in this directory
8. Run again!
        """)
        exit(1)
    
    # Search queries
    queries = [
        "Claude AI",
        "Claude AI amazing",
        "Claude AI helpful",
        "Anthropic Claude",
    ]
    
    # Run search (first run opens browser for OAuth)
    results = search_multiple_queries(queries, results_per_query=20)
    
    print(f"\n✅ Found {len(results)} unique tweets")
    
    # Save
    save_results(results)
    
    # Preview
    print("\n📋 Sample:")
    for r in results[:5]:
        print(f"  @{r.username}: {r.snippet[:80]}...")