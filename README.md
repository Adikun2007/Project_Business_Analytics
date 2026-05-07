# 🚀 Company Intelligence & Scoring Pipeline (WIP)

## 📌 What I am building

I am building a company intelligence pipeline that helps me:
- collect company data from public sources
- structure it into a clean dataset
- enrich missing fields (description, revenue, founder, etc.)
- score companies using a custom C1–C6 system
- continuously improve logic based on real-world testing

This project is still in development and evolving through iteration.

---

## 🧪 How I started

I started with AI-generated dummy data to:
- test my CSV structure
- validate scoring functions
- check how my pipeline behaves with sample inputs
- debug early logic issues

This helped me build a base before working with real companies.

---

## 📊 Current dataset structure

I am currently using the following format:

```csv
company,website,city,segment,description,revenue,founder,notes

```

## Field meaning:
- company → company name
- website → official or reference link
- city → location (still inconsistent, being cleaned)
- segment → industry category
- description → what the company does (fact-based)
- revenue → estimated revenue bucket
- founder → founder/director info if available
- notes → extra signals like growth, export, hiring, expansion

---

## 💰 Revenue logic

I classify companies into simple revenue buckets:

- <30 Cr
- 30–100 Cr
- 100–200 Cr
- 200–300 Cr
- 300-400 Cr
- 400-500 Cr

---

## 🧠 C1–C6 Scoring System

I use a custom scoring system to evaluate companies:

- C1 → Manufacturing strength
- C2 → India relevance
- C3 → Differentiation / niche strength
- C4 → Technical strength of founder / decision makers
- C5 → Company scale
- C6 → Growth and momentum signals

Each score outputs:

Weak / Moderate / Strong
Numeric score (0 / 10 / 20)

---

## 🔍 How I collect data

Right now, I manually:

- search companies from public sources (Tofler, CompanyCheck, websites)
- extract structured information:
-- segment
-- city
-- revenue
-- founder/directors
- enrich missing fields using inference
- add notes based on:
-- growth
-- exports
-- production scale
-- certifications

---

## 📌 Current status

This project is in an active development phase.

I am continuously:

- adding new companies
- testing scoring logic
- fixing edge cases
- refining dataset structure
- improving scoring accuracy

---

## 🎯 End goal

The goal is to build a simple but powerful system that can:

- identify high-value companies
- structure real-world company data
- score companies using meaningful business signals
- help prioritize companies for analysis or targeting
