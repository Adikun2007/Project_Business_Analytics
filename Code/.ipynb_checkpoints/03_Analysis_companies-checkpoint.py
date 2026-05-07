import pandas as pd
import re

# ========================= CONFIG =========================
INPUT_CSV = "cleaned_data.csv"
OUTPUT_CSV = "scored_companies_final.csv"

# ====================== SCORING FUNCTIONS ======================
def get_evidence(text, keywords):
    """Return matching keywords as evidence"""
    if pd.isna(text) or not text:
        return ""
    text_lower = str(text).lower()
    found = [k for k in keywords if k in text_lower]
    return ", ".join(found) if found else ""

def score_c1_manufacturing(description):
    """C1: Manufacturing Strength"""
    if pd.isna(description):
        return "Weak", 0, ""
    
    keywords_strong = ["manufacture", "manufacturer", "production", "plant", "facility", "factory"]
    evidence = get_evidence(description, keywords_strong)
    
    if evidence:
        return "Strong", 12, evidence
    return "Weak", 0, ""

def score_c2_city(city):
    """C2: Location"""
    if pd.isna(city):
        return "Weak", 0, ""
    return "Strong", 8, str(city)

def score_c3_technology(description):
    """C3: Technology & Specialty"""
    if pd.isna(description):
        return "Weak", 0, ""
    
    keywords = ["r&d", "research", "enzyme", "proprietary", "patent", "fermentation", "specialty", "advanced", "high purity"]
    evidence = get_evidence(description, keywords)
    
    if len(evidence.split(", ")) >= 2:
        return "Strong", 25, evidence
    elif evidence:
        return "Moderate", 15, evidence
    return "Weak", 0, ""

def score_c4_founder(founder):
    """C4: Founder Quality"""
    if pd.isna(founder) or str(founder).strip() == "":
        return "Weak", 0, ""
    
    founder_lower = str(founder).lower()
    strong_keywords = ["phd", "dr.", "dr ", "prof", "chemist", "scientist", "engineer", "technologist"]
    evidence = get_evidence(founder, strong_keywords)
    
    if evidence:
        return "Strong", 22, evidence
    return "Moderate", 10, "Founder mentioned"

def score_c5_segment(segment):
    """C5: Segment Fit"""
    if pd.isna(segment):
        return "Weak", 0, ""
    
    strong = ["biotech", "specialty chemicals", "performance chemicals", "pharma", "fine chemicals"]
    evidence = get_evidence(segment, strong)
    
    if evidence:
        return "Strong", 20, evidence
    return "Moderate", 12, str(segment)

def score_c6_notes(notes):
    """C6: Growth Signals"""
    if pd.isna(notes) or str(notes).strip() == "":
        return "Weak", 0, ""
    
    strong_keywords = ["expansion", "new plant", "capacity", "cagr", "funding", "growth", "export", "scale-up"]
    moderate_keywords = ["certification", "iso", "export", "established"]
    
    strong_ev = get_evidence(notes, strong_keywords)
    mod_ev = get_evidence(notes, moderate_keywords)
    
    if strong_ev:
        return "Strong", 23, strong_ev
    elif mod_ev:
        return "Moderate", 12, mod_ev
    return "Weak", 5, "Basic info only"

# ====================== MAIN ANALYSIS ======================
def main():
    print("Loading cleaned_data.csv...")
    df = pd.read_csv(INPUT_CSV)
    
    results = []
    
    for _, row in df.iterrows():
        c1_name, c1_score, c1_ev = score_c1_manufacturing(row.get("description"))
        c2_name, c2_score, c2_ev = score_c2_city(row.get("city"))
        c3_name, c3_score, c3_ev = score_c3_technology(row.get("description"))
        c4_name, c4_score, c4_ev = score_c4_founder(row.get("founder"))
        c5_name, c5_score, c5_ev = score_c5_segment(row.get("segment"))
        c6_name, c6_score, c6_ev = score_c6_notes(row.get("notes"))
        
        total_score = c1_score + c2_score + c3_score + c4_score + c5_score + c6_score
        
        # Final Verdict
        if total_score >= 85:
            verdict = "A+ - Excellent"
        elif total_score >= 75:
            verdict = "A - Strong Target"
        elif total_score >= 60:
            verdict = "B - Good Potential"
        elif total_score >= 45:
            verdict = "C - Average"
        else:
            verdict = "D - Low Priority"
        
        results.append({
            "company": row.get("company"),
            "website": row.get("website"),
            "city": row.get("city"),
            "revenue": row.get("revenue"),
            "founder": row.get("founder"),
            "C1_Manufacturing": c1_name,
            "C1_Score": c1_score,
            "C1_Evidence": c1_ev,
            "C2_City": c2_name,
            "C2_Score": c2_score,
            "C3_Technology": c3_name,
            "C3_Score": c3_score,
            "C3_Evidence": c3_ev,
            "C4_Founder": c4_name,
            "C4_Score": c4_score,
            "C4_Evidence": c4_ev,
            "C5_Segment": c5_name,
            "C5_Score": c5_score,
            "C5_Evidence": c5_ev,
            "C6_Growth": c6_name,
            "C6_Score": c6_score,
            "C6_Evidence": c6_ev,
            "Total_Score": total_score,
            "Verdict": verdict,
            "Notes": row.get("notes")
        })
    
    result_df = pd.DataFrame(results)
    
    # Sort by score
    result_df = result_df.sort_values(by="Total_Score", ascending=False)
    
    result_df.to_csv(OUTPUT_CSV, index=False)
    
    print(f"\n✅ Analysis completed! {len(result_df)} companies scored.")
    print(f"📁 Saved as: {OUTPUT_CSV}")
    print("\nTop 10 Companies:")
    print(result_df[["company", "Total_Score", "Verdict", "revenue"]].head(10))

if __name__ == "__main__":
    main()