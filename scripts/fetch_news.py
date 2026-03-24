#!/usr/bin/env python3
"""
Fetch AI news from RSS feeds worldwide and generate news-data.json.
Runs daily via GitHub Actions.

Dependencies: feedparser, requests (installed in workflow)
"""

import json
import re
import hashlib
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import feedparser
    import requests
except ImportError:
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "feedparser", "requests"])
    import feedparser
    import requests


# ── RSS Feed Sources ──
# Categorized by region and topic focus
FEEDS = [
    # North America
    {
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "source": "TechCrunch",
        "region": "North America",
        "default_category": "Industry",
    },
    {
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "source": "The Verge",
        "region": "North America",
        "default_category": "Industry",
    },
    {
        "url": "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "source": "Ars Technica",
        "region": "North America",
        "default_category": "Research",
    },
    {
        "url": "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml",
        "source": "MIT News",
        "region": "North America",
        "default_category": "Research",
    },
    {
        "url": "https://www.wired.com/feed/tag/ai/latest/rss",
        "source": "WIRED",
        "region": "North America",
        "default_category": "Industry",
    },
    {
        "url": "https://openai.com/blog/rss.xml",
        "source": "OpenAI Blog",
        "region": "North America",
        "default_category": "Research",
    },
    {
        "url": "https://blog.google/technology/ai/rss/",
        "source": "Google AI Blog",
        "region": "North America",
        "default_category": "Research",
    },
    # Europe
    {
        "url": "https://www.bbc.co.uk/search/rss?q=artificial+intelligence",
        "source": "BBC",
        "region": "Europe",
        "default_category": "Policy",
    },
    {
        "url": "https://www.theguardian.com/technology/artificialintelligenceai/rss",
        "source": "The Guardian",
        "region": "Europe",
        "default_category": "Policy",
    },
    {
        "url": "https://deepmind.google/blog/rss.xml",
        "source": "Google DeepMind",
        "region": "Europe",
        "default_category": "Research",
    },
    # Asia
    {
        "url": "https://www.scmp.com/rss/36/feed",
        "source": "South China Morning Post",
        "region": "Asia",
        "default_category": "Industry",
    },
    # Academic / Ethics
    {
        "url": "https://hai.stanford.edu/news/rss.xml",
        "source": "Stanford HAI",
        "region": "North America",
        "default_category": "Ethics",
    },
    # Education
    {
        "url": "https://www.edsurge.com/articles_rss",
        "source": "EdSurge",
        "region": "North America",
        "default_category": "Education",
    },
]


# ── Category Classification Keywords ──
CATEGORY_KEYWORDS = {
    "Research": [
        "study", "paper", "research", "scientists", "discovery", "breakthrough",
        "arxiv", "experiment", "findings", "published", "journal", "algorithm",
        "benchmark", "model", "neural", "dataset", "training", "LLM",
        "transformer", "diffusion", "reasoning", "multimodal",
    ],
    "Policy": [
        "regulation", "law", "government", "congress", "EU", "ban", "legislation",
        "compliance", "policy", "senate", "house", "executive order", "GDPR",
        "copyright", "antitrust", "regulate", "oversight", "governance",
        "safety", "act", "bill", "supreme court", "FTC",
    ],
    "Ethics": [
        "bias", "fairness", "ethical", "privacy", "surveillance", "deepfake",
        "misinformation", "disinformation", "responsible", "harm", "equity",
        "justice", "discrimination", "transparency", "accountability",
        "human rights", "social impact",
    ],
    "Education": [
        "education", "student", "teacher", "school", "university", "classroom",
        "learning", "curriculum", "academic", "faculty", "higher education",
        "coursework", "cheating", "plagiarism", "tutoring",
    ],
    "Tools": [
        "launch", "release", "app", "product", "feature", "update", "tool",
        "platform", "API", "chatbot", "assistant", "plugin", "integration",
        "ChatGPT", "Claude", "Gemini", "Copilot", "Midjourney", "DALL-E",
        "Sora", "Stable Diffusion",
    ],
    "Industry": [
        "startup", "funding", "acquisition", "billion", "million", "IPO",
        "company", "enterprise", "market", "business", "revenue", "valuation",
        "partnership", "CEO", "hire", "layoff", "investor",
    ],
}


def classify_article(title: str, description: str, default: str) -> str:
    """Classify an article into a category based on keyword matching."""
    text = f"{title} {description}".lower()
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            scores[category] = score

    if not scores:
        return default

    return max(scores, key=scores.get)


def is_ai_related(title: str, description: str) -> bool:
    """Filter to only AI-related articles."""
    text = f"{title} {description}".lower()
    ai_terms = [
        "ai", "artificial intelligence", "machine learning", "deep learning",
        "neural network", "chatgpt", "gpt", "llm", "language model",
        "generative ai", "gen ai", "openai", "anthropic", "claude",
        "gemini", "copilot", "midjourney", "dall-e", "stable diffusion",
        "computer vision", "natural language", "nlp", "transformer",
        "diffusion model", "reinforcement learning", "robot", "automation",
        "deepfake", "ai safety", "ai ethics", "ai regulation",
        "ai policy", "ai education", "ai tool", "ai assistant",
        "foundation model", "multimodal", "reasoning model",
    ]
    return any(term in text for term in ai_terms)


def clean_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"&[a-z]+;", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def generate_id(title: str, link: str) -> str:
    """Generate a unique ID for deduplication."""
    raw = f"{title}{link}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def parse_date(entry) -> str:
    """Extract and normalize publication date."""
    for field in ["published_parsed", "updated_parsed"]:
        parsed = getattr(entry, field, None)
        if parsed:
            try:
                dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass

    for field in ["published", "updated"]:
        val = getattr(entry, field, None)
        if val:
            return val

    return datetime.now(timezone.utc).isoformat()


def fetch_feed(feed_config: dict, cutoff_date: datetime) -> list:
    """Fetch and parse a single RSS feed."""
    url = feed_config["url"]
    source = feed_config["source"]
    region = feed_config["region"]
    default_cat = feed_config["default_category"]

    articles = []

    try:
        print(f"  Fetching: {source} ({url[:60]}...)")
        parsed = feedparser.parse(
            url,
            request_headers={"User-Agent": "NYU-Silver-AI-News-Bot/1.0"},
        )

        if parsed.bozo and not parsed.entries:
            print(f"    Warning: Feed error for {source}: {parsed.bozo_exception}")
            return []

        for entry in parsed.entries[:15]:  # Max 15 per feed
            title = clean_html(getattr(entry, "title", ""))
            description = clean_html(
                getattr(entry, "summary", getattr(entry, "description", ""))
            )
            link = getattr(entry, "link", "")

            if not title or not link:
                continue

            # Check if AI-related (for general feeds)
            if source in ["Ars Technica", "BBC", "The Guardian", "EdSurge",
                          "South China Morning Post"]:
                if not is_ai_related(title, description):
                    continue

            # Check date cutoff (7 days)
            pub_date = parse_date(entry)
            try:
                pub_dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                if pub_dt < cutoff_date:
                    continue
            except Exception:
                pass

            # Classify
            category = classify_article(title, description, default_cat)

            # Truncate description
            if len(description) > 300:
                description = description[:297].rsplit(" ", 1)[0] + "..."

            article_id = generate_id(title, link)

            articles.append({
                "id": article_id,
                "title": title,
                "description": description,
                "link": link,
                "source": source,
                "region": region,
                "category": category,
                "published": pub_date,
            })

    except Exception as e:
        print(f"    Error fetching {source}: {e}")

    print(f"    Found {len(articles)} AI articles from {source}")
    return articles


def deduplicate(articles: list) -> list:
    """Remove duplicate articles based on similar titles."""
    seen_ids = set()
    seen_titles = set()
    unique = []

    for article in articles:
        # Skip exact ID duplicates
        if article["id"] in seen_ids:
            continue

        # Skip very similar titles (lowercase, stripped of punctuation)
        title_key = re.sub(r"[^a-z0-9]", "", article["title"].lower())[:60]
        if title_key in seen_titles:
            continue

        seen_ids.add(article["id"])
        seen_titles.add(title_key)
        unique.append(article)

    return unique


def main():
    print("=" * 50)
    print("NYU Silver AI News Fetcher")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 50)

    # Only include articles from the last 7 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    all_articles = []

    for feed_config in FEEDS:
        articles = fetch_feed(feed_config, cutoff)
        all_articles.extend(articles)

    print(f"\nTotal raw articles: {len(all_articles)}")

    # Deduplicate
    all_articles = deduplicate(all_articles)
    print(f"After deduplication: {len(all_articles)}")

    # Sort by date (newest first)
    all_articles.sort(
        key=lambda a: a.get("published", ""),
        reverse=True,
    )

    # Cap at 50 articles max
    all_articles = all_articles[:50]

    # Build output
    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "source_count": len(set(a["source"] for a in all_articles)),
        "region_count": len(set(a["region"] for a in all_articles)),
        "article_count": len(all_articles),
        "articles": all_articles,
    }

    # Write JSON
    output_path = Path(__file__).parent.parent / "news-data.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(all_articles)} articles to {output_path}")
    print("Done!")


if __name__ == "__main__":
    main()
