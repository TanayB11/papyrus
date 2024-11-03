# app.py
import os
from datetime import datetime, timedelta
from dateutil.parser import parse
import xml.etree.ElementTree as ET

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from contextlib import asynccontextmanager
import requests
import uvicorn
import duckdb
import asyncio
import httpx
import json
import feedparser

import numpy as np
from svm import SVMModel, gen_embeddings_data, gen_svm_data


# ================================================
# DATABASE SETUP
# ================================================
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

MAX_ARTICLES = 500


# ================================================
# HELPER METHODS
# ================================================
async def parse_feed(feed_url: str, feed_name: str):
    """
    Updates the articles table with new articles from a feed
    """
    parsed_articles = []
    current_time = datetime.now()

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(feed_url)
        parsed_feed = feedparser.parse(response.text)
    except:
        raise HTTPException(status_code=500, detail=f'Error parsing feed {feed_url}')

    
    num_parsed_articles = 0

    # lots of jank parsing stuff here
    for item in parsed_feed.entries:
        title = item.title if 'title' in item else None
        url = item.link if 'link' in item else None

        description = None
        if 'content' in item:
            description = item.content[0].value
        elif 'description' in item:
            description = item.description
            if type(description) == tuple:
                description = description[0]
            else:
                description = None

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

        db.execute("""
            INSERT INTO articles (feed_name, feed_url, title, url, description, date, is_liked)
            VALUES (?, ?, ?, ?, ?, ?, FALSE)
            ON CONFLICT (url) DO UPDATE SET
                feed_name = EXCLUDED.feed_name,
                feed_url = EXCLUDED.feed_url,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                date = EXCLUDED.date
        """, [feed_name, feed_url, title, url, description, date])

        num_parsed_articles += 1
        if num_parsed_articles >= MAX_ARTICLES:
            break

    db.execute("UPDATE feeds SET timestamp = ? WHERE url = ?", [current_time, feed_url])


# ================================================
# FASTAPI SETUP
# ================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Speeds up startup time by pre-loading the database
    """
    feeds = db.sql("SELECT url, name FROM feeds").fetchall()
    tasks = [parse_feed(feed[0], feed[1]) for feed in feeds]
    await asyncio.gather(*tasks)

    yield

    db.close()

app = FastAPI(lifespan=lifespan)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================================================
# MODELING SETUP
# ================================================
model = SVMModel()
VISUALIZE_PCA = True

def fit_svm(model: SVMModel):
    """
    Fits the SVM model on the given articles

    Args:
        model (SVMModel): The SVM model to fit
        all_articles (list[dict]): The list of all articles (from the articles table, dictionary format)
    
    Returns:
        bool: Whether the SVM model was successfully fitted
    """
    if model.train_embeddings(gen_embeddings_data(db)):
        X, y = gen_svm_data(db)
        if X is not None and y is not None:
            model.train_svm(model.embed(X), y, visualize=VISUALIZE_PCA)
            return True

    return False


# ================================================
# CACHING
# ================================================
CACHE_TTL = timedelta(minutes=5)


# ================================================
# ROUTES
# ================================================
@app.get('/api/get_feeds')
async def get_feeds():
    """
    Get all feeds.

    Returns:
        list[(id, url, name)]: The list of RSS feeds
    """
    try:
        return db.sql('SELECT * FROM feeds').fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/all_articles')
async def get_all_articles(page_num: int, items_per_page: int):
    """
    Get items from all feeds, paginated.

    Args:
        page_num (int): The page number to retrieve (zero-indexed)
        items_per_page (int): The number of items per page

    Returns:
        dict{items, total_pages}: The items and total number of pages
    """
    try:
        all_feeds = db.sql("""
            SELECT json_object(
                'id', id,
                'url', url,
                'name', name,
                'timestamp', timestamp
            ) as feed 
            FROM feeds
        """).fetchall()
        feeds = [json.loads(feed[0]) for feed in all_feeds]

        # populate articles table
        tasks = [
            parse_feed(feed['url'], feed['name']) for feed in feeds
            if datetime.now() - datetime.fromisoformat(feed['timestamp']) > CACHE_TTL
        ]

        await asyncio.gather(*tasks)

        all_articles = db.execute("""
            SELECT json_object(
                'name', feed_name,
                'title', title,
                'url', url, 
                'date', date,
                'is_liked', is_liked,
                'description', description
            ) as article
            FROM articles 
            ORDER BY COALESCE(date, '1900-01-01') DESC
            LIMIT ?
        """, [MAX_ARTICLES]).fetchall()
        all_articles = [json.loads(article[0]) for article in all_articles]

        trained_svm = fit_svm(model)

        parsed_articles = []
        for article in all_articles:
            # we need something to embed
            if trained_svm and (article['description'] or article['title']):
                embeddings = model.embed([
                    (article['description'] or '') + ' ' + (article['title'] or '')
                ])
                embeddings = np.array(embeddings)
                svm_prob = model.predict(embeddings)
            else:
                svm_prob = 0.5 # ambivalent

            parsed_articles.append({
                **article,
                'svm_prob': svm_prob
            })

        # calculate pagination
        start_idx = page_num * items_per_page
        end_idx = start_idx + items_per_page

        sorted_items = sorted(
            parsed_articles[start_idx:end_idx],
            key=lambda x: (-x['svm_prob'], -datetime.fromisoformat(x['date'] or '1900-01-01').timestamp())
        )

        return {
            'items': sorted_items,
            'total_pages': len(parsed_articles) // items_per_page
        }
    except Exception as e:
        raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/create_feed')
async def create_feed(feed_url: str, feed_name: str):
    try:
        db.execute("""
            INSERT INTO feeds (id, url, name, timestamp) 
            VALUES (nextval('feed_id_seq'), ?, ?, ?)
        """, [feed_url, feed_name, datetime.min])

        return {"message": "Feed created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete('/api/delete_feed/{feed_url:path}')
async def delete_feed(feed_url: str):
    try:
        db.execute("DELETE FROM feeds WHERE url = ?", [feed_url])
        db.execute("DELETE FROM articles WHERE feed_url = ?", [feed_url])
        return {"message": "Feed deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/toggle_like_article')
async def toggle_like_article(url: str):
    """
    Toggles the liked status of an article
    """
    try:
        db.execute("UPDATE articles SET is_liked = NOT is_liked WHERE url = ?", [url])
        return {"message": f"Like status toggled successfully for {url}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    port = os.getenv('PORT', 2430)
    uvicorn.run(app, host="0.0.0.0", port=port)
