import os
import base64
import mimetypes
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import requests # <-- ADDED: For making API calls

# Load environment variables
load_dotenv()
# NOTE: Using OPENAI_API_KEY as the Gemini API Key as per your configuration
GEMINI_API_KEY = os.getenv("OPENAI_API_KEY") 
GEMINI_MODEL = "gemini-2.5-flash-preview-09-2025"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

TMP_DIR = Path("/tmp/llm_attachments")
TMP_DIR.mkdir(parents=True, exist_ok=True)

def decode_attachments(attachments):
    """
    attachments: list of {name, url: data:<mime>;base64,<b64>}
    Saves files into /tmp/llm_attachments/<name>
    Returns list of dicts: {"name": name, "path": "/tmp/..", "mime": mime, "size": n}
    """
    saved = []
    for att in attachments or []:
        name = att.get("name") or "attachment"
        url = att.get("url", "")
        if not url.startswith("data:"):
            continue
        try:
            # Handle potential filename sanitization if needed, but for now use as-is
            header, b64data = url.split(",", 1)
            mime = header.split(";")[0].replace("data:", "")
            data = base64.b64decode(b64data)
            path = TMP_DIR / name
            with open(path, "wb") as f:
                f.write(data)
            saved.append({
                "name": name,
                "path": str(path),
                "mime": mime,
                "size": len(data)
            })
        except Exception as e:
            print("Failed to decode attachment", name, e)
    return saved

def summarize_attachment_meta(saved):
    """
    saved is list from decode_attachments.
    Returns a short human-readable summary string for the prompt.
    """
    summaries = []
    for s in saved:
        nm = s["name"]
        p = s["path"]
        mime = s.get("mime", "")
        try:
            if mime.startswith("text") or nm.endswith((".md", ".txt", ".json", ".csv")):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    if nm.endswith(".csv"):
                        # Read only a few lines for CSV preview
                        f.seek(0)
                        lines = [next(f).strip() for _ in range(min(3, sum(1 for line in f))) if f.tell() < 1000]
                        f.seek(0) # Reset pointer
                        preview = "\\n".join(lines)
                    else:
                        data = f.read(1000)
                        preview = data.replace("\n", "\\n")[:1000]
                summaries.append(f"- {nm} ({mime}): preview: {preview}")
            else:
                summaries.append(f"- {nm} ({mime}): {s['size']} bytes (Binary file, use as-is or encode to b64 if needed)")
        except Exception as e:
            summaries.append(f"- {nm} ({mime}): (could not read preview: {e})")
    return "\\n".join(summaries)

def _strip_code_block(text: str) -> str:
    """
    If text is inside triple-backticks, return inner contents. Otherwise return text as-is.
    Also handles optional language specifier (e.g., ```html).
    """
    if "```" in text:
        parts = text.split("```")
        # Find the first non-empty part after the opening ```
        for part in parts[1:]:
            if part.strip():
                # Strip optional language identifier (e.g., 'html\n')
                lines = part.split('\n', 1)
                if len(lines) > 1 and not lines[0].strip().startswith('<'):
                    return lines[1].strip()
                return part.strip()
    return text.strip()

def generate_readme_fallback(brief: str, checks=None, attachments_meta=None, round_num=1):
    checks_text = "\\n".join(checks or [])
    att_text = attachments_meta or ""
    return f"""# Auto-generated README (Round {round_num})

**Project brief:** {brief}

**Attachments:**
{att_text}

**Checks to meet:**
{checks_text}

## Setup
1. Open `index.html` in a browser.
2. No build steps required.

## Notes
This README was generated as a fallback because the LLM did not return a valid response.
"""

def generate_app_code(brief: str, attachments=None, checks=None, round_num=1, prev_readme=None):
    """
    Generate or revise an app using the Gemini API.
    - round_num=1: build from scratch
    - round_num=2: refactor based on new brief and previous README/code
    """
    saved = decode_attachments(attachments or [])
    attachments_meta = summarize_attachment_meta(saved)

    context_note = ""
    if round_num == 2 and prev_readme:
        context_note = f"\n### Previous README.md:\n{prev_readme}\n\nRevise and enhance this project according to the new brief below. The code must be modified to satisfy the new requirements.\n"
        
    user_prompt = f"""
You are a professional web developer assistant. You must output a single-file HTML application.

### Round
{round_num}

### Task
{brief}

{context_note}

### Attachments (if any)
The attached files are available in the repository root. Reference them directly by name (e.g., 'sample.png').
{attachments_meta}

### Evaluation checks (Ensure the generated app can pass these checks)
{checks or []}

### Output format rules:
1. Produce a complete, runnable, single-file HTML web app satisfying the brief.
2. Output must contain **two parts only**:
    - The complete content of the `index.html` file (must be valid HTML).
    - The complete content of the `README.md` file, which starts after a line containing exactly: `---README.md---`
3. If using code blocks, ensure only the required content is inside the block.
4. README.md must include: Overview, Setup, Usage, and (if Round 2) describe improvements made.
5. Do not include any commentary or extra text outside the `index.html` and `---README.md---` sections.
"""

    text = ""
    try:
        # Construct payload for the Gemini API call
        payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "systemInstruction": {
                "parts": [{"text": "You are a professional web developer assistant. Output must adhere strictly to the requested two-part format: 'index.html' content followed by '---README.md---' and then 'README.md' content. All code must be runnable in a single HTML file."}]
            }
        }
        headers = {'Content-Type': 'application/json'}
        params = {'key': GEMINI_API_KEY} 

        # Call the Gemini API using requests (assuming the environment allows it)
        response = requests.post(GEMINI_API_URL, headers=headers, params=params, json=payload, timeout=60)
        response.raise_for_status() # Raise an exception for bad status codes

        result = response.json()
        
        # Extract the generated text from the response structure
        text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        
        if not text:
             # Try to extract the reason for failure if possible, otherwise raise
             safety_reason = result.get('candidates', [{}])[0].get('finishReason', 'UNKNOWN')
             raise Exception(f"LLM response text was empty. Finish reason: {safety_reason}")
            
        print("✅ Generated code using Gemini API.")

    except requests.exceptions.RequestException as e:
        print(f"⚠ Gemini API request failed ({e.__class__.__name__}), using fallback HTML instead: {e}")
    except Exception as e:
        print(f"⚠ LLM API failed, using fallback HTML instead: {e}")
        
    if "---README.md---" in text:
        code_part, readme_part = text.split("---README.md---", 1)
        code_part = _strip_code_block(code_part)
        readme_part = _strip_code_block(readme_part)
    else:
        # Fallback for when the model doesn't follow the separator rule
        code_part = _strip_code_block(text)
        readme_part = generate_readme_fallback(brief, checks, attachments_meta, round_num)
        
    # Generate the fallback HTML if no code was produced or an error occurred
    if not code_part.strip().startswith('<'):
         code_part = f"""
<html>
  <head><title>Fallback App</title></head>
  <body>
    <h1>Hello (fallback)</h1>
    <p>This app was generated as a fallback because the LLM failed to produce valid HTML. Brief: {brief}</p>
  </body>
</html>
"""

    files = {"index.html": code_part, "README.md": readme_part}
    return {"files": files, "attachments": saved}
