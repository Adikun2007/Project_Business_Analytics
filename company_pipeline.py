"""
ULTIMATE Company Research Pipeline v2.0
=======================================
Focused on real Indian chemical/specialty chemical companies.
"""

import requests
from bs4 import BeautifulSoup
import json, re, time, random, argparse, os, sys
import pandas as pd
from urllib.parse import quote_plus, urljoin, urlparse
from tqdm import tqdm

# ========================= CONFIG =========================
import os
from dotenv import load_dotenv

load_dotenv("apikey.env")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
LLM_MODEL         = "google/gemini-2.0-flash-001"   # You can change to claude-3-haiku if you want

DEFAULT_SEGMENT   = "specialty chemicals"
DEFAULT_LOCATIONS = ["Pune", "Pune Maharashtra", "Pimpri Chinchwad", "Nashik", "Thane"]
DEFAULT_LIMIT     = 80

REQUEST_DELAY_MIN = 1.8
REQUEST_DELAY_MAX = 4.0
LLM_DELAY         = 1.2
MAX_SCRAPE_CHARS  = 18000

RAW_CSV     = "raw_companies.csv"
OUTPUT_CSV  = "cleaned_data.csv"
PROGRESS_F  = ".pipeline_progress.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
}

# ====================== UTILITIES ======================
def sleep_random(a=REQUEST_DELAY_MIN, b=REQUEST_DELAY_MAX):
    time.sleep(random.uniform(a, b))

def safe_get(url, timeout=15):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 429):
                time.sleep(8)
        except:
            time.sleep(3)
    return None

def extract_text(html_content, max_chars=MAX_SCRAPE_CHARS):
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = " ".join(soup.stripped_strings)
    return text[:max_chars]

def clean_company_name(name):
    if not name:
        return ""
    name = re.sub(r'\s+', ' ', name.strip())
    name = re.sub(r'(?i)\b(pvt\.? ltd|ltd|llp|private limited|limited|india|manufacturer|supplier|exporter|dealer)\b', '', name)
    name = re.sub(r'[-–—].*$', '', name)
    return name.strip()

def domain_from_url(url):
    try:
        return urlparse(url).netloc.replace("www.", "").lower()
    except:
        return ""

# ====================== DISCOVERY ======================
def search_duckduckgo(query, max_results=15):
    companies = []
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    r = safe_get(url)
    if not r:
        return companies

    soup = BeautifulSoup(r.text, "html.parser")
    for res in soup.select(".result__body")[:max_results]:
        title = res.select_one(".result__title")
        link = res.select_one(".result__url")
        if not title:
            continue
        name = clean_company_name(title.get_text())
        if len(name) < 6:
            continue
        website = link.get_text(strip=True) if link else ""
        companies.append({
            "company": name,
            "website": website,
            "city": "",
            "source": "duckduckgo",
            "description": ""
        })
    return companies

def build_company_list(segment, locations, limit):
    print(f"\n{'═'*70}")
    print(f"STAGE 1 — Discovering Real Companies")
    print(f"{'═'*70}\n")

    all_companies = []

    for loc in locations:
        queries = [
            f"{segment} manufacturers {loc} India",
            f"specialty chemicals company {loc}",
            f"chemical company {loc} Maharashtra -product -buy",
        ]
        for q in queries:
            print(f"[>] Searching: {q}")
            results = search_duckduckgo(q, max_results=12)
            all_companies.extend(results)
            sleep_random()

    # Deduplicate
    df = pd.DataFrame(all_companies)
    if df.empty:
        print("No companies found.")
        return df

    df["company"] = df["company"].apply(clean_company_name)
    df = df[df["company"].str.len() > 5]
    df["_domain"] = df["website"].apply(domain_from_url)
    
    df = df.drop_duplicates(subset=["company"], keep="first")
    df = df.drop_duplicates(subset=["_domain"], keep="first")
    df = df.drop(columns=["_domain"])

    df = df.head(limit).reset_index(drop=True)
    print(f"[✓] Final companies after cleaning: {len(df)}")

    df.to_csv(RAW_CSV, index=False)
    return df

# ====================== WEBSITE FINDER ======================
def find_website(company_name, city="Pune"):
    """Strong website finder + Revenue lookup"""
    print(f"    [→] Searching for {company_name}")
    
    queries = [
        f"{company_name} official website",
        f"{company_name} {city}",
        f"{company_name} Maharashtra"
    ]
    
    for q in queries:
        r = safe_get(f"https://html.duckduckgo.com/html/?q={quote_plus(q)}")
        if not r:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        
        for link in soup.select("a.result__url"):
            url = link.get_text(strip=True)
            if any(x in url for x in [".com", ".in", ".co.in"]) and not any(bad in url.lower() for bad in ["indiamart","justdial","facebook","linkedin"]):
                print(f"    [✓] Website found: {url}")
                return url
    return ""

# ====================== LLM EXTRACTION (Strong Prompt) ======================
def llm_extract(text, company_name, segment_hint=""):
    prompt = f"""
You are an expert Indian business analyst specializing in chemical companies.

Extract information from the provided website text about this company.

Company: {company_name}
Segment Hint: {segment_hint}

Return **ONLY** valid JSON. No extra text.

{{
  "company": "exact official name",
  "website": "primary website",
  "city": "main city in India",
  "segment": "Specialty Chemicals or similar",
  "description": "2-4 sentence professional summary",
  "revenue": "e.g. ₹185 Cr (FY24) or unknown",
  "founder": "Founder / Promoter name(s)",
  "notes": "Key insights: expansion, exports, certifications, new plant, funding etc."
}}

Rules:
- Use empty string "" if information is not found.
- Revenue must include year if possible.
- Be concise and factual.
- Never invent information.

TEXT:
{text}
"""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 700,
            },
            timeout=40
        )

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # Clean JSON
        content = re.sub(r"```json|```", "", content).strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return None
    except Exception as e:
        print(f"  [LLM Error] {e}")
        return None

def quick_revenue_lookup(company_name):
    """Advanced Revenue Lookup - Works like manual Google search"""
    print(f"    [→] Revenue Search: {company_name}")
    
    queries = [
        f"{company_name} revenue OR turnover OR sales OR funding",
        f"{company_name} annual revenue",
        f"{company_name} FY24 OR FY23 OR FY25"
    ]
    
    for query in queries:
        try:
            r = safe_get(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}", timeout=12)
            if not r:
                continue
                
            soup = BeautifulSoup(r.text, "html.parser")
            full_text = soup.get_text()[:15000]   # Search in first 15k chars
            
            # Multiple flexible patterns
            patterns = [
                r'(?:revenue|turnover|sales).*?(\$?\s*[\d,]+\.?\d*\s*[MKB]?)',
                r'(?:revenue|turnover|sales).*?(\₹?\s*[\d,]+\.?\d*\s*(?:Cr|Crore|Lakh|Million|Billion)?)',
                r'(\₹?\$?\s*[\d,]+\.?\d*\s*(?:Cr|Crore|M|Million|K))',
                r'(\d{1,4}\.?\d*\s*[MmBbKk]?)'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, full_text, re.I)
                if matches:
                    revenue_str = matches[0] if isinstance(matches[0], str) else matches[0][0]
                    print(f"    [✓] Revenue Found: {revenue_str}")
                    return revenue_str.strip()
                    
        except Exception as e:
            continue
            
    print("    [⚠] No revenue found")
    return ""

# ====================== ENRICHMENT ======================
def enrich_company(row, segment_hint=""):
    company_name = row.get("company", "")
    website = row.get("website", "")

    # 1. Find website if missing
    if not website or len(website) < 15:
        website = find_website(company_name, row.get("city", "Pune"))
        sleep_random()

    # 2. Scrape website
    text = ""
    if website:
        print(f"    [→] Scraping: {website}")
        r = safe_get(website)
        if r and r.status_code == 200:
            text = extract_text(r.text)

    # 3. LLM Enrichment
    extracted = llm_extract(text, company_name, segment_hint) if text else None

    result = {
        "company": company_name,
        "website": website,
        "city": row.get("city", "Pune"),
        "segment": segment_hint,
        "description": "",
        "revenue": "",
        "founder": "",
        "notes": ""
    }

        # After LLM extraction
    if extracted:
        for k in result.keys():
            if k in extracted and extracted[k]:
                result[k] = str(extracted.get(k)).strip()

    # Fallback / Additional Revenue Search
    if not result.get("revenue") or len(result.get("revenue", "")) < 3:
        result["revenue"] = quick_revenue_lookup(company_name)

    return result

# ====================== MAIN ======================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--segment", default=None)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-discovery", action="store_true")
    args = parser.parse_args()

    segment = args.segment or input(f"Segment [{DEFAULT_SEGMENT}]: ") or DEFAULT_SEGMENT

    if args.skip_discovery and os.path.exists(RAW_CSV):
        df = pd.read_csv(RAW_CSV).head(args.limit)
    else:
        df = build_company_list(segment, DEFAULT_LOCATIONS, args.limit)

    if df.empty:
        print("No companies found.")
        sys.exit(1)

    # Enrichment loop (same as before but with improved functions)
    print(f"\nStarting enrichment for {len(df)} companies...")
    enriched = []
    for i, row in tqdm(df.iterrows(), total=len(df)):
        print(f"\n[{i+1}/{len(df)}] {row['company']}")
        result = enrich_company(row, segment)
        enriched.append(result)
        time.sleep(random.uniform(1.5, 3))

    final_df = pd.DataFrame(enriched)
    final_df.to_csv(OUTPUT_CSV, index=False)
    print(f"\n✅ Completed! Saved {len(final_df)} companies to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()