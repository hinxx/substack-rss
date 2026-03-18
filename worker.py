import os
import json
import feedparser
import ollama
from datetime import datetime
from time import mktime
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
try:
    import google.generativeai as genai
except ImportError:
    genai = None

DATA_DIR = "data"
ARTICLES_FILE = os.path.join(DATA_DIR, "articles.json")
FEEDS_FILE = "feeds.json"

os.makedirs(DATA_DIR, exist_ok=True)

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return default
    return default

def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

class SubstackSummarizer:
    def __init__(self, model="llama3.1:8b"):
        self.model = model
        self.articles = load_json(ARTICLES_FILE, [])
        self.feeds = load_json(FEEDS_FILE, [])

    def _get_system_prompt(self, feed_url, feed_title, feed_description):
        for f in self.feeds:
            if f.get("url") == feed_url and f.get("prompt"):
                return f["prompt"]
                
        print(f"--- Generating custom system prompt for '{feed_title}' using {self.model} ---")
        meta_prompt = f"""
        You are an expert AI instruction designer. I have a blog/newsletter titled "{feed_title}".
        Its description is: "{feed_description}".
        
        Write a system prompt for an AI assistant that will summarize articles from this specific publication.
        The prompt should tell the AI to adopt an appropriate persona (e.g., financial analyst, tech reviewer, philosopher, etc.) based on the blog's theme.
        It should also instruct the AI to extract 3-4 bullet points of the most relevant information for this niche.
        
        Return ONLY the raw system prompt text. Do not include any conversational filler.
        """
        try:
            if self.model.startswith("gemini-") and genai:
                model = genai.GenerativeModel(self.model)
                response = model.generate_content(meta_prompt)
                generated_prompt = response.text.strip()
            else:
                response = ollama.generate(model=self.model, prompt=meta_prompt)
                generated_prompt = response.get('response', '').strip()

            found = False
            for f in self.feeds:
                if f.get("url") == feed_url:
                    f["prompt"] = generated_prompt
                    found = True
                    break
            if not found:
                self.feeds.append({"url": feed_url, "prompt": generated_prompt})
            save_json(FEEDS_FILE, self.feeds)
            return generated_prompt
        except Exception as e:
            print(f"Error generating system prompt: {e}")
            return f"You are an expert assistant. Summarize the following article from '{feed_title}', focusing on the main points and key takeaways."

    def _summarize_article(self, content, system_prompt):
        try:
            if self.model.startswith("gemini-") and genai:
                model = genai.GenerativeModel(self.model, system_instruction=system_prompt)
                response = model.generate_content(f"Post Content: {content}")
                return response.text
            else:
                prompt = f"{system_prompt}\n\nPost Content: {content}"
                response = ollama.generate(model=self.model, prompt=prompt, options={'num_ctx': 32768})
                return response.get('response', 'No summary generated.')
        except Exception as e:
            print(f"Error invoking LLM ({self.model}): {e}")
            return "Error generating summary."

    def fetch_and_process(self, rss_url):
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            print(f"No posts found or invalid RSS URL: {rss_url}")
            return

        existing_links = {a.get("link") for a in self.articles if a.get("link")}
        new_entries = [entry for entry in feed.entries if entry.link not in existing_links]
        
        if not new_entries:
            print(f"No new articles found for {rss_url}. Skipping.")
            return

        feed_title = feed.feed.get('title', 'Unknown Feed')
        raw_description = feed.feed.get('subtitle', feed.feed.get('description', 'No description available'))
        feed_description = BeautifulSoup(raw_description, "html.parser").get_text(separator=" ", strip=True)
        system_prompt = self._get_system_prompt(rss_url, feed_title, feed_description)
        
        for entry in new_entries:
            print(f"--- Processing New Article: {entry.title} ---")
            content = entry.get('content', [{'value': entry.get('summary', '')}])[0]['value']
            clean_content = BeautifulSoup(content, "html.parser").get_text(separator=" ", strip=True)

            max_chars = 60000
            if len(clean_content) > max_chars:
                clean_content = clean_content[:max_chars] + " ... [Content Truncated]"

            summary = self._summarize_article(clean_content, system_prompt)
            
            pub_date = datetime.now()
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime.fromtimestamp(mktime(entry.published_parsed))
                
            self.articles.append({
                "link": entry.link,
                "title": entry.title,
                "published_date": pub_date.strftime("%Y-%m-%d %H:%M:%S"),
                "summary": summary,
                "feed_name": feed_title
            })
            print(f"Saved summary for: {entry.title}\n")
            
        self.articles.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        save_json(ARTICLES_FILE, self.articles)

    def render_static_site(self):
        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template('template.html')
        
        articles_by_feed = {}
        for article in self.articles:
            feed_name = article.get("feed_name", "Unknown Feed")
            if feed_name not in articles_by_feed:
                articles_by_feed[feed_name] = []
            articles_by_feed[feed_name].append(article)
            
        html_out = template.render(
            articles_by_feed=articles_by_feed,
            last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html_out)
        print("Static site generated at index.html")

if __name__ == "__main__":
    MODEL_TO_USE = "llama3.1:8b"
    if genai and os.environ.get("GOOGLE_API_KEY"):
        try:
            genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
            MODEL_TO_USE = "gemini-2.5-flash"
            print(f"--- Configured to use Google GenAI model: {MODEL_TO_USE} ---")
        except Exception as e:
            print(f"--- An error occurred configuring Google GenAI: {e}. Using local Ollama model: {MODEL_TO_USE} ---")

    summarizer = SubstackSummarizer(model=MODEL_TO_USE)
    
    if not summarizer.feeds:
        default_urls = [
            "https://jimmysjournal.substack.com/feed",
            "https://mispricedassets.substack.com/feed",
        ]
        summarizer.feeds = [{"url": url, "prompt": ""} for url in default_urls]
        save_json(FEEDS_FILE, summarizer.feeds)

    for feed in summarizer.feeds:
        url = feed.get("url")
        if url:
            summarizer.fetch_and_process(url)
            
    summarizer.render_static_site()