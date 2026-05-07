"""
Quick-add tool
==============
Use this to manually add known company URLs / names to cleaned_data.csv
and re-run enrichment on just those rows.

Usage
-----
python add_companies.py
  → prompts you to paste company names/URLs one per line

python add_companies.py --urls "https://acme.com, https://beta.in"
python add_companies.py --names "Aarti Industries, Deepak Nitrite"

Works seamlessly with company_pipeline.py output.
"""

import argparse, os
import pandas as pd
from company_pipeline import (
    enrich_company, LLM_DELAY, OUTPUT_CSV, sleep_random, LLM_MODEL
)
import time

DEFAULT_SEGMENT = "specialty chemicals"
DEFAULT_CITY    = "Pune"


def manual_add(entries, segment, city):
    rows = []
    for e in entries:
        e = e.strip()
        if not e:
            continue
        if e.startswith("http"):
            rows.append({"company": e, "website": e, "city": city})
        else:
            rows.append({"company": e, "website": "",  "city": city})

    print(f"\nEnriching {len(rows)} companies...\n")
    enriched = []
    for i, row in enumerate(rows):
        print(f"[{i+1}/{len(rows)}] {row['company']}")
        result = enrich_company(row, segment_hint=segment)
        enriched.append(result)
        sleep_random()

    new_df = pd.DataFrame(enriched)

    # Merge with existing CSV
    if os.path.exists(OUTPUT_CSV):
        existing = pd.read_csv(OUTPUT_CSV)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["company"], keep="last")
        combined.to_csv(OUTPUT_CSV, index=False)
        print(f"\n[✓] Merged into {OUTPUT_CSV}  ({len(combined)} total rows)")
    else:
        new_df.to_csv(OUTPUT_CSV, index=False)
        print(f"\n[✓] Saved {len(new_df)} rows to {OUTPUT_CSV}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls",     default=None, help="Comma-separated company URLs")
    parser.add_argument("--names",    default=None, help="Comma-separated company names")
    parser.add_argument("--segment",  default=DEFAULT_SEGMENT)
    parser.add_argument("--city",     default=DEFAULT_CITY)
    args = parser.parse_args()

    entries = []
    if args.urls:
        entries += [u.strip() for u in args.urls.split(",")]
    if args.names:
        entries += [n.strip() for n in args.names.split(",")]

    if not entries:
        print("Paste company names or URLs, one per line. Empty line to finish:")
        while True:
            line = input()
            if not line.strip():
                break
            entries.append(line.strip())

    manual_add(entries, segment=args.segment, city=args.city)


if __name__ == "__main__":
    main()
