import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import re
import argparse
import subprocess
import os
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
}

PREVIOUS_CSV = "discovered_chemical_companies.csv"

def clean_company_name(name):
    if not name:
        return ""
    name = re.sub(r'\s+', ' ', name.strip())
    name = re.sub(r'(?i)\b(pvt\.? ltd|ltd|llp|private limited|limited|india|pune|mumbai|kg|powder|liquid|grade|technical|industrial|packaging|cas no|manufacturer)\b', '', name)
    name = re.sub(r'[-–—].*$', '', name)
    name = re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', name)
    return name.strip()

def clean_url(url):
    if not url or len(url) < 8 or "#" in url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    return url.strip().rstrip("/")

def get_soup(url, delay=True):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        if delay:
            time.sleep(random.uniform(1.8, 4))
        return BeautifulSoup(resp.text, 'html.parser')
    except Exception:
        return None

def load_previous_companies():
    if os.path.exists(PREVIOUS_CSV):
        try:
            df = pd.read_csv(PREVIOUS_CSV)
            return set(df['company'].str.lower().str.strip())
        except:
            return set()
    return set()

def scrape_maharashtra_directory():
    companies = []
    base = "https://www.maharashtradirectory.com"
    locations = ["pune", "mumbai", "nashik", "thane"]
    categories = ["chemicals", "speciality-chemicals"]

    print("🔍 Scraping Maharashtra Directory...")
    for loc in locations:
        for cat in categories:
            for page in range(1, 4):
                url = f"{base}/district/{loc}/{cat}.html"
                if page > 1:
                    url += f"?page={page}"
                
                soup = get_soup(url, delay=(page > 1))
                if not soup:
                    continue

                items = soup.select("a[href*='companyinfo']")
                for a_tag in items:
                    name = clean_company_name(a_tag.get_text())
                    if len(name) < 5:
                        continue
                    link = urljoin(base, a_tag.get("href", ""))
                    companies.append({
                        "company": name,
                        "website": clean_url(link),
                        "city": loc.capitalize(),
                        "source": "MaharashtraDirectory"
                    })
    return companies

def scrape_indiamart():
    companies = []
    urls = [
        "https://dir.indiamart.com/pune/speciality-chemicals.html",
        "https://dir.indiamart.com/mumbai/speciality-chemicals.html",
    ]
    print("🔍 Scraping IndiaMART...")
    for url in urls:
        soup = get_soup(url)
        if not soup:
            continue
        listings = soup.select("h2, .lst h2, a[href*='company']")
        for item in listings:
            name = clean_company_name(item.get_text())
            if len(name) < 6:
                continue
            link = clean_url(item.get("href", ""))
            companies.append({
                "company": name,
                "website": link,
                "city": "Maharashtra",
                "source": "IndiaMART"
            })
    return companies

def scrape_justdial():
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        print("🔍 Scraping Justdial...")
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument(f"user-agent={HEADERS['User-Agent']}")

        driver = webdriver.Chrome(options=options)
        driver.get("https://www.justdial.com/Pune/Speciality-Chemical-Manufacturers/nct-10446685")
        time.sleep(8)

        companies = []
        items = driver.find_elements(By.CSS_SELECTOR, ".jcn, .store-details")
        for item in items[:80]:
            try:
                name = clean_company_name(item.text.strip())
                if len(name) > 5:
                    companies.append({
                        "company": name,
                        "website": "",
                        "city": "Pune",
                        "source": "Justdial"
                    })
            except:
                continue
        driver.quit()
        return companies
    except Exception:
        print("   ⚠️ Justdial skipped (Selenium not available)")
        return []

def auto_run_add_companies(df, max_to_add):
    if len(df) == 0:
        return
    
    entries = []
    for _, row in df.head(max_to_add).iterrows():
        website = str(row.get("website", "")).strip()
        if website.startswith("http"):
            entries.append(website)
        else:
            entries.append(row["company"])

    entries_str = ",".join([e.replace('"', '').replace(',', ' ') for e in entries])
    
    print(f"\n🚀 Running enrichment on {len(entries)} companies (using 02_add_companies.py)...")

    try:
        # Correct filename with quotes for safety
        cmd = f'python "02_add_companies.py" --urls "{entries_str}" --segment "specialty chemicals" --city "Pune"'
        result = subprocess.run(cmd, shell=True, check=True)
        print("✅ Auto enrichment started successfully!")
    except Exception as e:
        print(f"❌ Auto-run failed: {e}")
        print("\n🔧 Run this command manually:")
        print(f'python "02_add_companies.py" --urls "{entries_str}"')

def main():
    print("🚀 Ultimate Chemical Company Finder + Enricher (Improved Control)\n")
    
    # Ask user how many companies they want
    while True:
        try:
            num = input("How many companies do you want to discover & enrich? (Recommended: 30-80): ")
            num_to_enrich = int(num)
            if 1 <= num_to_enrich <= 300:
                break
            print("Please enter a number between 1 and 300.")
        except:
            print("Please enter a valid number.")

    previous = load_previous_companies()
    print(f"Loaded {len(previous)} previously discovered companies.")

    all_companies = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(scrape_maharashtra_directory),
            executor.submit(scrape_indiamart),
        ]
        futures.append(executor.submit(scrape_justdial))
        
        for future in as_completed(futures):
            all_companies.extend(future.result())

    df = pd.DataFrame(all_companies)
    df = df[df["company"].str.len() > 5]
    df['company_lower'] = df['company'].str.lower().str.strip()
    df = df[~df['company_lower'].isin(previous)]
    df = df.drop_duplicates(subset=["company"], keep="first")
    df = df.drop(columns=['company_lower'], errors='ignore')

    df["has_website"] = df["website"].str.len() > 15
    df = df.sort_values(by="has_website", ascending=False)

    if len(df) > num_to_enrich:
        df = df.head(num_to_enrich)

    print(f"\n🎉 Found {len(df)} New Companies")
    print(df[["company", "website", "city", "source"]].head(15))

    df.to_csv(PREVIOUS_CSV, index=False)
    print(f"\n💾 Saved discovered companies to {PREVIOUS_CSV}")

    # Ask user whether to enrich now
    enrich_now = input("\nDo you want to enrich these companies now? (y/n): ").strip().lower()
    if enrich_now == 'y' or enrich_now == 'yes':
        auto_run_add_companies(df, max_to_add=len(df))
    else:
        print("\nYou can run enrichment later using:")
        print(f'python add_companies.py --names "{",".join(df["company"].head(60))}"')

if __name__ == "__main__":
    main()