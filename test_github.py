from github import Github, Auth
import os
import requests
from dotenv import load_dotenv

# Load .env
load_dotenv()

# --- Configuration Constants (Matching app/llm_generator.py) ---
GEMINI_MODEL = "gemini-2.5-flash-preview-09-2025"
# Note: Using OPENAI_API_KEY env var to hold the Gemini Key
GEMINI_API_KEY = os.getenv("OPENAI_API_KEY") 
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


# -------------------------
# Test GitHub
# -------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
USERNAME = os.getenv("GITHUB_USERNAME")

if GITHUB_TOKEN and USERNAME:
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)

        # Get authenticated user
        user = g.get_user()
        print(f"\n👤 GitHub Authenticated as: {user.login}")

        if user.login.lower() != USERNAME.lower():
            print(f"⚠️ Warning: .env username ({USERNAME}) doesn't match actual login ({user.login})")

        print("📂 Your first 5 GitHub repos:")
        for repo in user.get_repos()[:5]:
            print("-", repo.name)

    except Exception as e:
        print(f"\n❌ GitHub API failed to authenticate or connect: {e}")
else:
    print("\n❌ GITHUB_TOKEN or USERNAME environment variables are missing.")


# -------------------------
# Test Gemini/LLM API
# -------------------------
print("\n--- Test Gemini API Connection ---")

if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY (from OPENAI_API_KEY env) not found.")
else:
    try:
        # A simple generation request to confirm the API key is valid
        payload = {
            "contents": [{"parts": [{"text": "Say hello to me."}]}]
        }
        headers = {'Content-Type': 'application/json'}
        params = {'key': GEMINI_API_KEY}

        r = requests.post(GEMINI_API_URL, headers=headers, params=params, json=payload, timeout=15)
        r.raise_for_status() # Raise exception for 4xx or 5xx status codes

        result = r.json()
        
        # Check for successful generation (may vary based on model response structure)
        if result.get('candidates'):
            generated_text = result['candidates'][0]['content']['parts'][0]['text']
            print(f"✅ Gemini API Authenticated. Successfully contacted {GEMINI_MODEL}.")
            print(f"   LLM Response start: {generated_text.strip()[:50]}...")
        else:
            print(f"❌ Gemini API failed to return content. Full Response: {r.text[:200]}...")

    except requests.exceptions.HTTPError as e:
        print(f"❌ Gemini API failed with HTTP Error {e.response.status_code}. The response suggests an invalid key or model issue.")
    except Exception as e:
        print(f"❌ Gemini API failed: {e}")
