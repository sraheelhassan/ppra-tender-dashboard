"""
Scrapes active tenders from PPRA (Pakistan Public Procurement Regulatory Authority)
and saves them to data/tenders.csv with an auto-assigned category per tender.
"""
import re
import time
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://epms.ppra.gov.pk/public/tenders/active-tenders"
DETAIL_URL = "https://epms.ppra.gov.pk/public/tenders/tender-details/{}"
OUT_CSV = "data/tenders.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

CATEGORY_KEYWORDS = {
    "Construction/Works":   ["construct", "rehabilitat", "renovat", "wall", "fenc",
                              "civil work", "building", "infrastructure", "boundary"],
    "Medical/Health":       ["medicine", "health", "hospital", "medical", "kit",
                              "pharma", "drug", "histopatholog", "disposable"],
    "IT/Technology":        ["computer", "software", "i.t.", " it ", "system",
                              "digital", "electronic", "network", "server", "lab equipment"],
    "Energy/Utilities":     ["power", "energy", "gas", "electric", "solar", "fuel",
                              "petroleum", "lpg", "hvdc"],
    "Services":             ["service", "contract", "maintenance", "operation",
                              "security", "cleaning", "conservancy", "audit", "insurance"],
    "Defence/Military":     ["ammunition", "military", "paf", "navy", "army",
                              "defence", "cantt", "tyres", "tubes", "tank"],
    "Goods/Supplies":       ["purchase", "supply", "procurement", "equipment",
                              "material", "tool", "stationery", "spare"],
    "Auction/Land":         ["auction", "renting out", "land", "toll tax"],
}


def categorize(title: str, ppra_category: str = "") -> str:
    t = f"{title} {ppra_category}".lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return cat
    return "Other"


def parse_detail_cell(parts):
    """
    Tender Details cell is a variable-length list of text fragments:
      [title, description..., ppra_category, reference, org_name(dup)]
    The last element is always the org name (duplicated from the org cell),
    second-to-last is the reference number, third-to-last is PPRA's own category.
    """
    if not parts:
        return "", "", "", ""
    title = parts[0]
    org_dup = parts[-1] if len(parts) >= 2 else ""
    reference = parts[-2] if len(parts) >= 3 else ""
    ppra_category = parts[-3] if len(parts) >= 4 else ""
    description = " ".join(parts[1:-3]) if len(parts) > 4 else ""
    return title, description, ppra_category, reference


def parse_org_cell(parts):
    if not parts:
        return "", ""
    org_name = parts[0]
    location = parts[-1] if len(parts) >= 2 else ""
    return org_name, location


def parse_table(html: str):
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return []

    records = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 7:
            continue

        sr = tds[0].get_text(strip=True)
        tender_no = tds[1].get_text(strip=True)
        detail_parts = [p for p in tds[2].get_text(separator="|", strip=True).split("|") if p]
        org_parts = [p for p in tds[3].get_text(separator="|", strip=True).split("|") if p]
        status = tds[4].get_text(strip=True)
        advertised = tds[5].get_text(strip=True)
        closing_parts = [p for p in tds[6].get_text(separator="|", strip=True).split("|") if p]

        title, description, ppra_category, reference = parse_detail_cell(detail_parts)
        org_name, location = parse_org_cell(org_parts)
        closing_date = closing_parts[0] if closing_parts else ""
        closing_time = closing_parts[1] if len(closing_parts) > 1 else ""

        records.append({
            "sr": sr,
            "tender_number": tender_no,
            "title": title,
            "description": description,
            "ppra_category": ppra_category,
            "reference": reference,
            "organization": org_name,
            "location": location,
            "status": status,
            "advertised_date": advertised,
            "closing_date": closing_date,
            "closing_time": closing_time,
            "detail_url": DETAIL_URL.format(tender_no),
        })
    return records


def get_total_pages(html: str) -> int:
    m = re.search(r"Page\s+1\s+of\s+(\d+)", html, re.IGNORECASE)
    return int(m.group(1)) if m else 1


def scrape_all(max_pages: int = None, delay: float = 0.4, progress_cb=None):
    session = requests.Session()
    session.headers.update(HEADERS)

    first = session.get(BASE_URL, timeout=20)
    total_pages = get_total_pages(first.text)
    if max_pages:
        total_pages = min(total_pages, max_pages)

    all_records = []
    for page in range(1, total_pages + 1):
        html = first.text if page == 1 else session.get(
            BASE_URL, params={"page": page}, timeout=20
        ).text
        all_records.extend(parse_table(html))
        if progress_cb:
            progress_cb(page, total_pages)
        if page < total_pages:
            time.sleep(delay)

    df = pd.DataFrame(all_records)
    if not df.empty:
        df["category"] = df.apply(
            lambda r: categorize(r["title"], r.get("ppra_category", "")), axis=1
        )
        df["closing_dt"] = pd.to_datetime(
            df["closing_date"], format="%b %d, %Y", errors="coerce"
        )
    df["scraped_at"] = datetime.now().isoformat()
    return df


if __name__ == "__main__":
    print("Scraping PPRA active tenders...")
    df = scrape_all(progress_cb=lambda p, t: print(f"  page {p}/{t}"))
    df.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(df)} tenders to {OUT_CSV}")
