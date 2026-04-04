# Claude Growth Engine — HackNU 2026

## Reverse-engineering Claude's viral growth playbook

---

## QUICK START (do this right now)

### Step 1: Open your terminal

**Mac:** Press `Cmd + Space`, type `Terminal`, hit Enter
**Windows:** Press `Win + R`, type `cmd`, hit Enter (or use PowerShell)

### Step 2: Check if Python is installed

```bash
python3 --version
```

If you see `Python 3.x.x` — you're good. If not:
- **Mac:** `brew install python3` or download from python.org
- **Windows:** Download from https://www.python.org/downloads/ (check "Add to PATH")

### Step 3: Navigate to this folder

```bash
cd ~/Desktop/claude_growth
```
(or wherever you saved this folder)

### Step 4: Install dependencies

```bash
pip3 install -r requirements.txt
```

If that fails, try:
```bash
pip install -r requirements.txt
```

### Step 5: Run the Reddit scraper (NO API KEY NEEDED)

```bash
python3 scrapers/reddit_scraper.py
```

This takes ~3-5 minutes. It will print progress. Wait until you see "DONE!"
Output: `data/raw/reddit_data.csv` and `data/raw/reddit_data.json`

### Step 6: Run the YouTube scraper (needs free API key — 5 min setup)

1. Go to https://console.cloud.google.com/
2. Click "Select a project" at the top → "New Project" → name it anything → Create
3. Wait 10 seconds, then go to: APIs & Services → Library
4. Search "YouTube Data API v3" → Click it → Click "Enable"
5. Go to: APIs & Services → Credentials
6. Click "+ Create Credentials" → "API Key"
7. Copy the key

Then run:
```bash
python3 scrapers/youtube_scraper.py YOUR_API_KEY_HERE
```

This takes ~2-3 minutes. Output: `data/raw/youtube_data.csv`

### Step 7: Run the analysis (generates all charts)

```bash
python3 analysis/analysis.py
```

Charts saved to `analysis/charts/`. Open them to see your findings.

---

## TROUBLESHOOTING

**"ModuleNotFoundError: No module named 'requests'"**
→ Run: `pip3 install requests`

**"ModuleNotFoundError: No module named 'pandas'"**
→ Run: `pip3 install pandas matplotlib openpyxl`

**Reddit scraper shows "Rate limited"**
→ This is normal. It waits automatically and retries. Be patient.

**YouTube scraper says "API key not valid"**
→ Make sure you enabled the YouTube Data API v3 (Step 6.4 above)
→ Wait 1-2 minutes after creating the key before using it

**"Permission denied" on Mac**
→ Use `python3` instead of `python`
→ If pip fails: `pip3 install --user -r requirements.txt`

---

## PROJECT STRUCTURE

```
claude_growth/
├── scrapers/
│   ├── reddit_scraper.py      ← Run first (no API key)
│   └── youtube_scraper.py     ← Run second (free API key)
├── data/
│   ├── raw/                   ← Scraper outputs land here
│   └── clean/                 ← Cleaned datasets
├── analysis/
│   ├── analysis.py            ← Generates all charts
│   └── charts/                ← PNG visualizations
├── requirements.txt
└── README.md                  ← You are here
```
