import os
import json
import feedparser
import requests
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL,NVDA,MSFT,AMZN,GOOGL,TSLA,META,AMD&region=US&lang=en-US",
    "https://news.google.com/rss/search?q=when:1h+stock+market+OR+economy&hl=en-US&gl=US&ceid=US:en"
]

SEEN_ARTICLES_FILE = "seen_articles.json"

class TickerImpact(BaseModel):
    ticker: str = Field(description="İlgili hisse kodu (örn: NVDA, AAPL). Yoksa 'MACRO'")
    exchange: str = Field(description="NASDAQ, NYSE veya UNKNOWN")
    impact: str = Field(description="BULLISH, BEARISH veya NEUTRAL")
    confidence_score: float = Field(description="0.0 ile 1.0 arasında güven skoru")
    reasoning: str = Field(description="Haberin bu ticker üzerindeki etkisinin Türkçe özeti (Max 2 cümle)")

def load_seen_articles():
    if os.path.exists(SEEN_ARTICLES_FILE):
        try:
            with open(SEEN_ARTICLES_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen_articles(seen_set):
    with open(SEEN_ARTICLES_FILE, "w") as f:
        json.dump(list(seen_set)[-1000:], f)

def send_telegram_alert(analysis: TickerImpact, title: str, link: str):
    emoji = "🟢" if analysis.impact == "BULLISH" else "🔴" if analysis.impact == "BEARISH" else "⚪"
    message = (
        f"{emoji} **[{analysis.impact}] {analysis.ticker}** ({analysis.exchange})\n"
        f"**Güven Skoru:** {analysis.confidence_score * 100:.0f}%\n\n"
        f"**Haber:** {title}\n\n"
        f"**Analiz:** {analysis.reasoning}\n\n"
        f"🔗 [Habere Git]({link})"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram hatası: {e}")

client = genai.Client(api_key=GEMINI_API_KEY)

def analyze_news_item(title: str, summary: str) -> TickerImpact:
    prompt = f"Sen finansal analistsin. Haberi incele:\nBaşlık: {title}\nÖzet: {summary}\nEtkilenen birincil ticker ve yönü belirle."
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TickerImpact,
            temperature=0.1
        )
    )
    return TickerImpact.model_validate_json(response.text)

def main():
    seen_articles = load_seen_articles()
    print(f"Mevcut taranmış haber sayısı: {len(seen_articles)}")
    
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            article_id = entry.get("id", entry.link)
            if article_id in seen_articles:
                continue
            
            title = entry.title
            summary = entry.get("summary", "")
            link = entry.link
            print(f"İşleniyor: {title}")
            
            try:
                analysis = analyze_news_item(title, summary)
                if analysis.impact in ["BULLISH", "BEARISH"] and analysis.confidence_score >= 0.6:
                    send_telegram_alert(analysis, title, link)
            except Exception as e:
                print(f"Analiz hatası: {e}")
            
            seen_articles.add(article_id)
    
    save_seen_articles(seen_articles)

if __name__ == "__main__":
    main()