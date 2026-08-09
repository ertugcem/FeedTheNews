import os
import json
import feedparser
import requests
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Geniş Kapsamlı Haber Akışları (Tek tek kelime aratmak yerine geniş kategoriler)
RSS_FEEDS = [
    # 1. Mega-Cap Teknoloji Ticker'ları
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL,NVDA,MSFT,AMZN,GOOGL,TSLA,META,AMD,MU,SNDK&region=US&lang=en-US",
    # 2. Geniş Borsa, Makroekonomi ve Jeopolitik Akış
    "https://news.google.com/rss/search?q=when:1h+stock+market+OR+economy+OR+finance+OR+geopolitics&hl=en-US&gl=US&ceid=US:en",
    # 3. Yarı İletken, Teknoloji ve Sektörel Akış
    "https://news.google.com/rss/search?q=when:1h+semiconductor+OR+tech+OR+earnings&hl=en-US&gl=US&ceid=US:en"
]

SEEN_ARTICLES_FILE = "seen_articles.json"

# ---------------------------------------------------------------------------
# PYDANTIC OUTPUT SCHEMA
# ---------------------------------------------------------------------------
class TickerImpact(BaseModel):
    subject: str = Field(description="Haberin ana konusu veya kaynağı (Örn: 'Kospi / DRAM Uyarısı', 'FED Açıklaması', 'NVDA Bilanço')")
    ticker: str = Field(description="İlgili ABD hisse kodları veya makro etiketler (Örn: MU, NVDA, SPY, OIL)")
    impact_type: str = Field(description="BULLISH, BEARISH, NEUTRAL veya GEOPOLITICAL_RISK")
    confidence_score: float = Field(description="0.0 ile 1.0 arasında güven skoru")
    market_message: str = Field(description="Olayın piyasa, tedarik zinciri ve hisseler üzerindeki etkisini açıklayan net ve akıcı analiz (Türkçe)")

# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------
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
    if analysis.impact_type == "GEOPOLITICAL_RISK":
        emoji = "⚠️"
    elif analysis.impact_type == "BULLISH":
        emoji = "🟢"
    elif analysis.impact_type == "BEARISH":
        emoji = "🔴"
    else:
        emoji = "⚪"
    
    message = (
        f"{emoji} **[{analysis.subject}]** ({analysis.ticker})\n"
        f"**Piyasa Sinyali:** {analysis.impact_type}\n\n"
        f"📰 **Haber:** {title}\n\n"
        f"💬 **Analist Yorumu:** {analysis.market_message}\n\n"
        f"🔗 [Habere Git]({link})"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram hatası: {e}")

def send_system_status_message(status_text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": status_text,
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Status mesajı hatası: {e}")

# ---------------------------------------------------------------------------
# CORE AGENT LOGIC
# ---------------------------------------------------------------------------
client = genai.Client(api_key=GEMINI_API_KEY)

def analyze_news_item(title: str, summary: str) -> TickerImpact:
    prompt = f"""
    Sen küresel piyasalar, tedarik zincirleri ve makroekonomi konusunda uzmanlaşmış kıdemli bir Wall Street analistisin.
    
    Aşağıdaki haberi okumak ve ekonomi üzerindeki ikincil/üçüncül etkilerini (Second-order effects) analiz etmekle görevlisin:
    
    Haber Başlığı: {title}
    Haber Özeti: {summary}
    
    Analiz Kuralları:
    1. NEDENSELLİK ZİNCİRİ KUR: Haberde adı geçen bölge, şirket veya olayın (Örn: Kospi, TSMC, Orta Doğu, FED, gümrük vergileri) ABD borsalarında (NASDAQ/NYSE) doğrudan veya dolaylı KİMİ etkileyeceğini tespit et.
       - Örnek: Kore/Kospi DRAM uyarısı -> Micron ($MU) ve bellek sektörü etkilenir.
       - Örnek: Tayvan/Çip aksaması -> Nvidia ($NVDA) ve Apple ($AAPL) etkilenir.
       - Örnek: Jeopolitik/Siyasi kriz -> Genel piyasa ($SPY), petrol veya ilgili sektör etkilenir.
       
    2. MESAJ TONU: 'market_message' alanına doğrudan durumu özetleyen şu tonda akıcı bir Türkçe analiz yaz:
       "Piyasaya şöyle bir haber/açıklama düştü; bunun tedarik zinciri/sektör üzerindeki etkisi nedeniyle [ilgili varlıklar/ticker'lar] üzerinde [şu yönde] bir etkisi olacaktır..."
       
    3. TİCKER SEÇİMİ: Haberin en çok etki edeceği birincil US Ticker'ı veya makro etiketi (Örn: MU, NVDA, SPY, OIL) belirle.
    """
    
    response = client.models.generate_content(
        model="gemini-flash",
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
                # Anlamlı ve yeterli güven skoruna sahip analizleri bildir
                if analysis.confidence_score >= 0.6:
                    send_telegram_alert(analysis, title, link)
                    print(f"-> Telegram Gönderildi: {analysis.subject} [{analysis.impact_type}]")
            except Exception as e:
                print(f"Analiz hatası: {e}")
            
            seen_articles.add(article_id)
    
    save_seen_articles(seen_articles)

    # ---------------------------------------------------------------------------
    # HER ÇALIŞMADA BİLDİRİM / HEARTBEAT MESAJI
    # ---------------------------------------------------------------------------
    if new_alerts_sent == 0:
        send_system_status_message("ℹ️ Ajan çalıştı: Yeni/kritik haber bulunamadı.")

if __name__ == "__main__":
    main()
