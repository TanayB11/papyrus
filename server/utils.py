import duckdb
import httpx

from datetime import timedelta, datetime
from cachetools import TTLCache

# ================================================
# CONSTANTS
# ================================================
MAX_ARTICLES = 500
VISUALIZE_PCA = True # generates figures when training model

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
# CACHING
# ================================================
CACHE_TTL = timedelta(minutes=5)
article_cache = TTLCache(maxsize=500, ttl=CACHE_TTL.total_seconds())
liked_article_cache = TTLCache(maxsize=1, ttl=CACHE_TTL.total_seconds())
svm_cache = TTLCache(maxsize=1, ttl=CACHE_TTL.total_seconds())


# ================================================
# RSS FEED PARSING
# ================================================
def get_articles_to_insert(parsed_feed):
    """
    Helper method for parse_feed
    Prepares a list of articles to insert into the database

    Args:
        parsed_feed (feedparser.FeedParserDict): The parsed RSS feed from feedparser
    """
    articles_to_insert = []

    num_parsed_articles = 0
    for item in parsed_feed.entries:
        title = item.title if 'title' in item else None
        url = item.link if 'link' in item else None

        # get article description/content
        description = None
        if 'content' in item:
            description = item.content[0].value
        elif 'description' in item:
            description = item.description
            if type(description) == tuple:
                description = description[0]
            else:
                description = None

        # get article published date
        date_str = None
        if 'published' in item:
            date_str = item.published
        elif 'updated' in item:
            date_str = item.updated
        elif 'pubDate' in item:
            date_str = item.pubDate

        try:
            date = parse(date_str).strftime('%Y-%m-%d') if date_str else None
        except:
            date = None

        articles_to_insert.append((feed_name, feed_url, title, url, description, date))
        num_parsed_articles += 1
        if num_parsed_articles >= MAX_ARTICLES:
            break
    
    return articles_to_insert


async def parse_feed(db: duckdb.duckdb, feed_url: str, feed_name: str):
    """
    Updates the articles table with new articles from a feed
    """
    parsed_articles = []
    current_time = datetime.now()

    # get the feed XML
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(feed_url)
        parsed_feed = feedparser.parse(response.text)
    except:
        return

    articles_to_insert = get_articles_to_insert(parsed_feed)

    # update database
    if articles_to_insert:
        # execute batch insert by expanding the VALUES clause for each article
        placeholders = ','.join(['(?, ?, ?, ?, ?, ?, FALSE)'] * len(articles_to_insert))
        # flatten the list of tuples into a single list of values
        values = [val for tup in articles_to_insert for val in tup]
        
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
