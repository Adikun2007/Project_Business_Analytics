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
You are an expert Indian chemical industry researcher.

Company: {company_name}
Segment: {segment_hint}

Extract information and return **ONLY** valid JSON:

{{
  "company": "...",
  "website": "...",
  "city": "...",
  "segment": "...",
  "description": "2-4 sentence summary",
  "revenue": "any revenue, turnover, or sales figure you can find (e.g. ₹242 Cr, 40L-1.5Cr, 10-50 Cr etc.) or leave empty string if not found",
  "founder": "...",
  "notes": "key business details, products, certifications, exports, expansion etc."
}}

If nothing found for a field, put empty string "".

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

def estimate_revenue_from_employees(company_name, text=""):
    """Improved Employee Count Detection + Revenue Estimation"""
    if not text:
        return "unknown"
    
    print(f"    [→] Trying to estimate revenue via employee count for: {company_name}")
    
    # Much better patterns for employee detection
    employee_patterns = [
        r'(\d{1,4})\s*employees?',
        r'employs?\s*(\d{1,4})',
        r'team of\s*(\d{1,4})',
        r'(\d{1,4})\s*people',
        r'(\d{1,4})\s*staff',
        r'over\s*(\d{1,4})\s*employees',
        r'about\s*(\d{1,4})\s*employees',
        r'(\d{2,4})\s*member',
    ]
    
    emp_count = None
    for pattern in employee_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            try:
                emp_count = int(match.group(1))
                print(f"    [✓] Detected {emp_count} employees")
                break
            except:
                continue
    
    if not emp_count or emp_count < 5:
        return "unknown"
    
    # More aggressive estimation (as per your preference)
    if emp_count <= 20:
        est = "15-40 Cr"
    elif emp_count <= 50:
        est = "50-120 Cr"           # ~100 Cr for 50 employees
    elif emp_count <= 100:
        est = "100-250 Cr"
    elif emp_count <= 200:
        est = "200-500 Cr"
    else:
        est = f"~{int(emp_count * 2.2)} Cr"
    
    final_estimate = f"~{est} (est. based on {emp_count} employees)"
    print(f"    [→] Employee-based Revenue Estimate: {final_estimate}")
    
    return final_estimate
    
def quick_revenue_lookup(company_name):
    print(f"    [→] Revenue Search: {company_name}")
    
    queries = [
        f"{company_name} revenue OR turnover OR crore OR tofler",
        f"{company_name} \"annual turnover\"",
        f"{company_name} zaubacorp",
        f"{company_name} financials OR FY24"
    ]
    
    for query in queries:
        try:
            r = safe_get(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}", timeout=20)
            if not r: 
                continue
                
            text = BeautifulSoup(r.text, "html.parser").get_text()[:30000]
            
            # Strong patterns
            patterns = [
                r'(\d{1,4}\.?\d*)\s*(?:Cr|Crore)',
                r'(\₹?\$?[\d,]+\.?\d*)\s*(Cr|Crore|Lakh|Million)',
                r'(?:turnover|revenue).*?(\d{1,4}\.?\d*)',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text, re.I)
                if matches:
                    revenue = str(matches[0]).strip() if isinstance(matches[0], str) else str(matches[0][0])
                    if len(revenue) >= 2:
                        print(f"    [✓] Revenue Found → {revenue}")
                        return revenue + " Cr (approx)"
        except:
            continue
            
    return "unknown"

# ====================== ENRICHMENT ======================
def enrich_company(row, segment_hint=""):
    company_name = row.get("company", "")
    website = row.get("website", "")

    # 1. Find website if missing
    if not website or len(str(website)) < 15:
        website = find_website(company_name, row.get("city", "Pune"))
        sleep_random()

        # 2. Improved Scraping - Try multiple pages
    text = ""
    if website:
        print(f"    [→] Scraping: {website}")
        pages_to_try = [website]
        
        # Add common financial/about pages
        parsed = urlparse(website)
        base = f"{parsed.scheme}://{parsed.netloc}"
        extra_pages = ["/about", "/about-us", "/investors", "/financials", "/annual-report"]
        
        for slug in extra_pages:
            pages_to_try.append(base + slug)
        
        for page_url in pages_to_try[:5]:
            r = safe_get(page_url)
            if r and r.status_code == 200:
                page_text = extract_text(r.text, max_chars=8000)
                text += " " + page_text
                print(f"    [✓] Scraped extra page: {page_url}")
                sleep_random(0.8, 1.5)

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

    # Merge LLM output
    if extracted:
        for k in ["company", "website", "city", "segment", "description", "revenue", "founder", "notes"]:
            if k in extracted and extracted.get(k):
                result[k] = str(extracted.get(k)).strip()

    if not result.get("revenue") or str(result.get("revenue")).strip() in ["", "unknown", "N/A"]:
        result["revenue"] = quick_revenue_lookup(company_name)

    if not result.get("revenue") or str(result.get("revenue")).strip() in ["", "unknown", "N/A"]:
        result["revenue"] = estimate_revenue_from_employees(company_name, text)   # ← This should now work better

    return result   # ← This was missing in some paths
    # 1. Find website if


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