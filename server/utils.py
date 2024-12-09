import duckdb
import httpx
import json
import feedparser

from datetime import timedelta, datetime
from dateutil.parser import parse

# ================================================
# CONSTANTS
# ================================================
MAX_ARTICLES = 500
VISUALIZE_PCA = True # generates figures when training model
ARTICLE_REFRESH_INTERVAL = 60 # time (minutes) to automatically grab articles and train svm


# ================================================
# DATABASE SETUP
# ================================================
def setup_db():
    db = duckdb.connect('./data/papyrus.db') # optimistic concurrency control by default

    db.execute("CREATE SEQUENCE IF NOT EXISTS feed_id_seq;")
    db.execute("CREATE SEQUENCE IF NOT EXISTS article_id_seq;")

    db.execute("""
        CREATE TABLE IF NOT EXISTS feeds (
            id INTEGER PRIMARY KEY DEFAULT nextval('feed_id_seq'),
            url VARCHAR,
            name VARCHAR,
            timestamp TIMESTAMP
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY DEFAULT nextval('article_id_seq'),
            feed_name VARCHAR,
            feed_url VARCHAR,
            title VARCHAR,
            url VARCHAR UNIQUE,
            date DATE,
            description VARCHAR,
            is_liked BOOLEAN,
        )
    """)

    return db


# ================================================
# RSS FEED PARSING
# ================================================
async def parse_one_feed(feed: dict):
    """
    Prepares a list of articles to insert into the database

    Args:
        feed (dict): RSS feed containing (url, name, etc.)
    """
    feed_articles = []

    # get the RSS XML
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(feed['url'])
        parsed_feed = feedparser.parse(response.text)
    except Exception as e:
        raise e
        return
    
    num_parsed_articles = 0
    for article in parsed_feed.entries:
        article_title = article.title if 'title' in article else None
        article_url = article.link if 'link' in article else None

        # get article description/content
        description = None
        if 'content' in article:
            description = article.content[0].value
        elif 'description' in article:
            description = article.description
            if type(description) == tuple:
                description = description[0]
            else:
                description = None

        # get article published date
        date_str = None
        if 'published' in article:
            date_str = article.published
        elif 'updated' in article:
            date_str = article.updated
        elif 'pubDate' in article:
            date_str = article.pubDate

        try:
            date = parse(date_str).strftime('%Y-%m-%d') if date_str else None
        except:
            date = None

        feed_articles.append((feed['name'], feed['url'], article_title, article_url, description, date))
        num_parsed_articles += 1
        if num_parsed_articles >= MAX_ARTICLES:
            break
    
    return feed_articles


async def parse_all_feeds(db: duckdb.duckdb):
    """
    Updates the articles table with new articles from a feed
    """
    parsed_articles = []
    current_time = datetime.now()

    # get the feed URLs
    all_feeds = db.sql("""
        SELECT json_object(
            'url', url,
            'name', name,
            'timestamp', timestamp
        ) as feed 
        FROM feeds
    """).fetchall()
    feeds = [json.loads(feed[0]) for feed in all_feeds]

    for feed in feeds:
        feed_articles = await parse_one_feed(feed)

        feed_url = feed['url']
        feed_name = feed['name']

        # update database
        if feed_articles:
            placeholders = ','.join(['(?, ?, ?, ?, ?, ?, FALSE)'] * len(feed_articles)) # batch insert
            values = [val for tup in feed_articles for val in tup] # flatten
            
            db.execute(f"""
                INSERT INTO articles (feed_name, feed_url, title, url, description, date, is_liked)
                SELECT * FROM (
                    VALUES {placeholders}
                ) AS tmp(feed_name, feed_url, title, url, description, date, is_liked)
                ON CONFLICT (url) DO UPDATE SET
                    feed_name = EXCLUDED.feed_name,
                    feed_url = EXCLUDED.feed_url,
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    date = EXCLUDED.date
            """, values)

        db.execute("UPDATE feeds SET timestamp = ? WHERE url = ?", [current_time, feed_url])
