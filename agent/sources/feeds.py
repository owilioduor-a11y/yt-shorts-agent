"""Curated, mostly-free RSS feed catalog grouped by niche.

These are the same publishers named in the brief (BleepingComputer, CoinDesk,
TechCrunch, GitHub) plus high-signal community feeds. RSS is the safest way to
source news: it is parsing-friendly, rate-limit friendly and always links back
to the original publisher for attribution.
"""

FEEDS = {
    "cybersecurity": [
        ("BleepingComputer", "https://www.bleepingcomputer.com/feed/"),
        ("The Hacker News", "https://feeds.feedburner.com/TheHackersNews"),
        ("Krebs on Security", "https://krebsonsecurity.com/feed/"),
        ("Dark Reading", "https://www.darkreading.com/rss.xml"),
        ("SecurityWeek", "https://www.securityweek.com/feed/"),
        ("CISA Advisories", "https://www.cisa.gov/cybersecurity-advisories/all.xml"),
        ("Hacker News Security", "https://hnrss.org/newest?q=security"),
    ],
    "programming": [
        ("GitHub Blog", "https://github.blog/feed/"),
        ("Hacker News", "https://hnrss.org/frontpage"),
        ("Dev.to", "https://dev.to/feed"),
        ("InfoQ", "https://feed.infoq.com/"),
        ("Stack Overflow Blog", "https://stackoverflow.blog/feed/"),
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("Lobsters", "https://lobste.rs/rss"),
    ],
    "crypto": [
        ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("Cointelegraph", "https://cointelegraph.com/rss"),
        ("Decrypt", "https://decrypt.co/feed"),
        ("The Block", "https://www.theblock.co/rss.xml"),
        ("Bitcoin Magazine", "https://bitcoinmagazine.com/feed/"),
        ("CoinJournal", "https://coinjournal.net/feed/"),
    ],
}

# Keyword hints used to bias scoring toward "breaking / high-engagement" items.
HOT_KEYWORDS = {
    "cybersecurity": [
        "zero-day", "zero day", "exploit", "ransomware", "breach", "hacked",
        "vulnerability", "cve-", "malware", "phishing", "patch", "backdoor",
        "supply chain", "leak", "critical",
    ],
    "programming": [
        "release", "launch", "v1", "1.0", "open source", "opensource", "rust",
        "python", "javascript", "typescript", "golang", "ai", "compiler",
        "framework", "breaking", "deprecat", "security",
    ],
    "crypto": [
        "bitcoin", "btc", "ethereum", "eth", "etf", "sec", "halving", "surge",
        "crash", "all-time high", "ath", "regulation", "spot", "hack", "stablecoin",
        "solana", "ripple", "xrp",
    ],
}
