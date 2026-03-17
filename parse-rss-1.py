import sqlite3
import feedparser
import ollama
from datetime import datetime
from time import mktime
import time
import threading
from flask import Flask, render_template_string, request, redirect, url_for
from bs4 import BeautifulSoup


class SubstackSummarizer:
    def __init__(self, rss_url, db_path="summaries.db", model="llama3.1:8b"):
        self.rss_url = rss_url
        self.db_path = db_path
        self.model = model
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database and table if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS articles (
                    link TEXT PRIMARY KEY,
                    title TEXT,
                    published_date DATETIME,
                    summary TEXT,
                    feed_name TEXT
                )
            ''')
            # Safely add the column for backwards compatibility with existing database
            try:
                cursor.execute("ALTER TABLE articles ADD COLUMN feed_name TEXT DEFAULT 'Unknown'")
            except sqlite3.OperationalError:
                pass
                
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS feed_prompts (
                    feed_url TEXT PRIMARY KEY,
                    prompt TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS feeds (
                    url TEXT PRIMARY KEY
                )
            ''')
            conn.commit()
            
    def _get_system_prompt(self, feed_url, feed_title, feed_description):
        """Retrieves or dynamically generates a tailored system prompt for the feed."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT prompt FROM feed_prompts WHERE feed_url = ?", (feed_url,))
            row = cursor.fetchone()
            if row:
                return row[0]
            
            print(f"--- Generating custom system prompt for '{feed_title}' ---")
            meta_prompt = f"""
            You are an expert AI instruction designer. I have a blog/newsletter titled "{feed_title}".
            Its description is: "{feed_description}".
            
            Write a system prompt for an AI assistant that will summarize articles from this specific publication.
            The prompt should tell the AI to adopt an appropriate persona (e.g., financial analyst, tech reviewer, philosopher, etc.) based on the blog's theme.
            It should also instruct the AI to extract 3-4 bullet points of the most relevant information for this niche.
            
            Return ONLY the raw system prompt text. Do not include any conversational filler.
            """
            try:
                response = ollama.generate(model=self.model, prompt=meta_prompt)
                generated_prompt = response.get('response', '').strip()
                cursor.execute("INSERT INTO feed_prompts (feed_url, prompt) VALUES (?, ?)", (feed_url, generated_prompt))
                conn.commit()
                return generated_prompt
            except Exception as e:
                print(f"Error generating system prompt: {e}")
                return f"You are an expert assistant. Summarize the following article from {feed_title}, focusing on the main points and key takeaways."

    def fetch_and_process(self):
        """Fetches the RSS feed, checks against the DB, and processes new articles."""
        feed = feedparser.parse(self.rss_url)
        if not feed.entries:
            print("No posts found or invalid RSS URL.")
            return

        feed_title = feed.feed.get('title', 'Unknown Feed')
        
        # Extract and clean the feed description to inform the LLM
        raw_description = feed.feed.get('subtitle', feed.feed.get('description', 'No description available'))
        feed_description = BeautifulSoup(raw_description, "html.parser").get_text(separator=" ", strip=True)
        
        system_prompt = self._get_system_prompt(self.rss_url, feed_title, feed_description)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for entry in feed.entries:
                link = entry.link
                title = entry.title
                
                # Check if the article has already been processed
                cursor.execute("SELECT 1 FROM articles WHERE link = ?", (link,))
                if cursor.fetchone() is not None:
                    print(f"Skipping already processed article: {title}")
                    continue
                
                print(f"--- Processing New Article: {title} ---")
                
                # Substack puts full text in 'content', fallback to 'summary'
                content = entry.get('content', [{'value': entry.get('summary', '')}])[0]['value']
                
                # Remove HTML tags to provide clean text to Ollama
                clean_content = BeautifulSoup(content, "html.parser").get_text(separator=" ", strip=True)

                # Limit content length to avoid exceeding the LLM context window (~60k chars is approx 15k tokens)
                max_chars = 60000
                print(f"Original content length: {len(clean_content)} characters.")
                if len(clean_content) > max_chars:
                    clean_content = clean_content[:max_chars] + " ... [Content Truncated]"
                    print(f"Content truncated to {max_chars} characters for Ollama processing.")

                # Generate summary
                summary = self._summarize_article(clean_content, system_prompt)
                
                # Parse published date robustly
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_date = datetime.fromtimestamp(mktime(entry.published_parsed))
                else:
                    published_date = datetime.now()
                    
                # Save the result to the local DB
                cursor.execute('''
                    INSERT INTO articles (link, title, published_date, summary, feed_name)
                    VALUES (?, ?, ?, ?, ?)
                ''', (link, title, published_date, summary, feed_title))
                conn.commit()
                print(f"Saved summary for: {title}\n")

    def _summarize_article(self, content, system_prompt):
        """Invokes Ollama to generate a summary of the provided text."""
        prompt = f"""
        {system_prompt}

        Post Content: {content}
        """
        try:
            response = ollama.generate(model=self.model, prompt=prompt,
                                        options={
                                            'num_ctx': 32768  # Sets the window to Mistral's max capacity
                                        }
                                    )
            return response.get('response', 'No summary generated.')
        except Exception as e:
            print(f"Error invoking Ollama: {e}")
            return "Error generating summary."


app = Flask(__name__)
DB_PATH = "summaries.db"
last_updated_time = "Never"

def fetch_all_feeds():
    """Iterates through all feeds in the database, processes new articles, and updates the timestamp."""
    global last_updated_time
    print("\n--- Running fetch ---")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM feeds")
        feeds = [row[0] for row in cursor.fetchall()]
        
    for url in feeds:
        try:
            summarizer = SubstackSummarizer(rss_url=url, db_path=DB_PATH)
            summarizer.fetch_and_process()
        except Exception as e:
            print(f"Error during fetch for {url}: {e}")
    last_updated_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@app.route("/")
def index():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, link, published_date, summary, feed_name FROM articles ORDER BY published_date DESC")
        rows = cursor.fetchall()
        
        cursor.execute("SELECT feed_url, prompt FROM feed_prompts")
        prompts = cursor.fetchall()

    # Group articles by their feed_name
    articles_by_feed = {}
    for row in rows:
        title, link, pub_date, summary, feed_name = row
        if feed_name not in articles_by_feed:
            articles_by_feed[feed_name] = []
        articles_by_feed[feed_name].append({
            "title": title, "link": link, "pub_date": pub_date, "summary": summary
        })

    html_template = """
    <html>
    <head>
        <title>Substack Summaries</title>
        <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f9; color: #333; }
            .tab { overflow: hidden; border: 1px solid #ccc; background-color: #e0e0e0; border-radius: 8px 8px 0 0; }
            .tab button { background-color: inherit; float: left; border: none; outline: none; cursor: pointer; padding: 14px 16px; transition: 0.3s; font-size: 17px; font-weight: bold; }
            .tab button:hover { background-color: #ccc; }
            .tab button.active { background-color: #fff; border-bottom: 2px solid #fff; }
            .tabcontent { display: none; padding: 20px; border: 1px solid #ccc; border-top: none; background-color: #fff; border-radius: 0 0 8px 8px; }
            .article { background: #fafafa; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #eee; }
            h2 { margin-top: 0; }
            h2 a { color: #0056b3; text-decoration: none; }
            h2 a:hover { text-decoration: underline; }
            .date { color: #888; font-size: 0.9em; margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 10px; }
            .post-link { margin-bottom: 15px; font-size: 0.9em; word-break: break-all; }
            .post-link a { color: #0056b3; text-decoration: none; }
            .summary { line-height: 1.6; }
            .summary p { margin-top: 0; margin-bottom: 1em; }
            .summary p:last-child { margin-bottom: 0; }
        </style>
    </head>
    <body>
        <h1>Substack Article Summaries</h1>
        <div style="display: flex; align-items: center; gap: 15px; margin-top: -20px; margin-bottom: 20px;">
            <p style="font-size: 0.9em; color: #666; margin: 0;">Last fetch: {{ last_updated }}</p>
            <form action="{{ url_for('refresh') }}" method="POST" style="margin: 0;">
                <button type="submit" style="padding: 5px 10px; background-color: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.8em; font-weight: bold;">Refresh Now</button>
            </form>
            <form action="{{ url_for('add_feed') }}" method="POST" style="margin: 0; display: flex; gap: 5px;">
                <input type="url" name="feed_url" placeholder="New RSS URL..." required style="padding: 5px; border: 1px solid #ccc; border-radius: 4px; width: 250px;">
                <button type="submit" style="padding: 5px 10px; background-color: #0056b3; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.8em; font-weight: bold;">Add Feed</button>
            </form>
        </div>
        {% if articles_by_feed %}
            <div class="tab">
                {% for feed_name in articles_by_feed.keys() %}
                <button class="tablinks {% if loop.first %}active{% endif %}" onclick="openTab(event, 'tab_{{ loop.index }}')">{{ feed_name }}</button>
                {% endfor %}
                <button class="tablinks" onclick="openTab(event, 'tab_prompts')">⚙️ System Prompts</button>
            </div>
            
            {% for feed_name, articles in articles_by_feed.items() %}
            <div id="tab_{{ loop.index }}" class="tabcontent" {% if loop.first %}style="display:block"{% endif %}>
                {% for article in articles %}
                <div class="article">
                    <h2><a href="{{ article.link }}" target="_blank">{{ article.title }}</a></h2>
                    <div class="date">Published: {{ article.pub_date }}</div>
                    <div class="summary">{{ article.summary }}</div>
                </div>
                {% endfor %}
            </div>
            {% endfor %}
            
            <div id="tab_prompts" class="tabcontent">
                <h2>Edit System Prompts</h2>
                <p>Customize the instruction prompts used by Ollama for each specific feed.</p>
                {% for feed_url, prompt in prompts %}
                <div class="article">
                    <h3>{{ feed_url }}</h3>
                    <form action="{{ url_for('update_prompt') }}" method="POST">
                        <input type="hidden" name="feed_url" value="{{ feed_url }}">
                        <textarea name="prompt" rows="8" style="width: 100%; padding: 10px; margin-bottom: 10px; font-family: monospace; border: 1px solid #ccc; border-radius: 4px; resize: vertical;">{{ prompt }}</textarea><br>
                        <button type="submit" style="padding: 10px 20px; background-color: #0056b3; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">Save Prompt</button>
                    </form>
                </div>
                {% endfor %}
            </div>
        {% else %}
            <p>No summaries available yet.</p>
        {% endif %}
        <script>
          function openTab(evt, tabId) {
            var i, tabcontent, tablinks;
            tabcontent = document.getElementsByClassName("tabcontent");
            for (i = 0; i < tabcontent.length; i++) {
              tabcontent[i].style.display = "none";
            }
            tablinks = document.getElementsByClassName("tablinks");
            for (i = 0; i < tablinks.length; i++) {
              tablinks[i].className = tablinks[i].className.replace(" active", "");
            }
            document.getElementById(tabId).style.display = "block";
            evt.currentTarget.className += " active";
          }
          
          document.addEventListener('DOMContentLoaded', (event) => {
            document.querySelectorAll('.summary').forEach(function(element) {
              element.innerHTML = marked.parse(element.textContent || '');
            });
          });
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template, articles_by_feed=articles_by_feed, prompts=prompts, last_updated=last_updated_time)

@app.route("/update_prompt", methods=["POST"])
def update_prompt():
    feed_url = request.form.get("feed_url")
    new_prompt = request.form.get("prompt")
    if feed_url and new_prompt:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE feed_prompts SET prompt = ? WHERE feed_url = ?", (new_prompt, feed_url))
            conn.commit()
    return redirect(url_for('index'))

@app.route("/refresh", methods=["POST"])
def refresh():
    """Manually trigger a fetch sequence and reload the page."""
    fetch_all_feeds()
    return redirect(url_for('index'))

@app.route("/add_feed", methods=["POST"])
def add_feed():
    """Adds a new feed to the database, fetches it, and reloads the page."""
    feed_url = request.form.get("feed_url")
    if feed_url:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS feeds (url TEXT PRIMARY KEY)")
            cursor.execute("INSERT OR IGNORE INTO feeds (url) VALUES (?)", (feed_url,))
            conn.commit()
            
        try:
            summarizer = SubstackSummarizer(rss_url=feed_url, db_path=DB_PATH)
            summarizer.fetch_and_process()
        except Exception as e:
            print(f"Error fetching new feed {feed_url}: {e}")
    return redirect(url_for('index'))

if __name__ == "__main__":
    # Seed the database with default feeds if it's currently empty
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feeds (
                url TEXT PRIMARY KEY
            )
        ''')
        cursor.execute("SELECT count(*) FROM feeds")
        if cursor.fetchone()[0] == 0:
            default_feeds = [
                "https://jimmysjournal.substack.com/feed",
                "https://mispricedassets.substack.com/feed",
                "https://aimaker.substack.com/feed",
                "https://defytheodds88.substack.com/feed",
                "https://tspasemiconductor.substack.com/feed",
                "https://mphinance.substack.com/feed",
                "https://jasonschips.substack.com/feed",
                "https://tscsw.substack.com/feed",
                "https://reboundcapital.substack.com/feed"
            ]
            for f in default_feeds:
                cursor.execute("INSERT INTO feeds (url) VALUES (?)", (f,))
            conn.commit()

    def background_fetch():
        """Background task that fetches new RSS feeds periodically."""
        while True:
            fetch_all_feeds()
            time.sleep(3 * 60 * 60)  # Sleep for 3 hours
    
    print("--- Starting background fetch thread ---")
    fetch_thread = threading.Thread(target=background_fetch, daemon=True)
    fetch_thread.start()
    
    print("--- Starting Flask Server ---")
    app.run(debug=True, host="0.0.0.0", port=5001, use_reloader=False)
