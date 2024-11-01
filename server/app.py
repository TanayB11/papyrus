# app.py
import os
from datetime import datetime, timedelta
from dateutil.parser import parse
import xml.etree.ElementTree as ET

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import requests
import uvicorn
import duckdb
import asyncio
import httpx
import json

import numpy as np
from svm import SVMModel, gen_embeddings_data, gen_svm_data

# ================================================
# FASTAPI SETUP
# ================================================
app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================================================
# DATABASE SETUP
# ================================================
db = duckdb.connect('./data/papyrus.db')

db.execute("CREATE SEQUENCE IF NOT EXISTS feed_id_seq;")
db.execute("CREATE SEQUENCE IF NOT EXISTS article_id_seq;")

db.execute("""
    CREATE TABLE IF NOT EXISTS feeds (
        id INTEGER PRIMARY KEY DEFAULT nextval('feed_id_seq'),
        url VARCHAR,
        name VARCHAR
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
        is_liked BOOLEAN
    )
""")

# ================================================
# MODELING SETUP
# ================================================

model = SVMModel()
VISUALIZE_PCA = True

def fit_svm(model: SVMModel, all_articles: list[dict]):
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
        model.train_svm(model.embed(X), y, visualize=VISUALIZE_PCA)
        return True

    return False

# ================================================
# CACHING
# ================================================

feed_cache = {} # key: feed_url, value: (timestamp, XML data)
CACHE_TTL = timedelta(minutes=1)


# ================================================
# ROUTES
# ================================================
@app.get('/get_feeds')
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


async def parse_feed(feed_url: str, feed_name: str):
    """
    Updates the articles table with new articles from a feed
    """
    parsed_articles = []

    try: # get and parse xml
        current_time = datetime.now()
        xml_content = None

        if feed_url in feed_cache:
            timestamp, xml_content = feed_cache[feed_url]
            if current_time - timestamp < CACHE_TTL:
                return # no need to repopulate the tables
            feed_cache.pop(feed_url)
            xml_content = None

        if xml_content is None:
            async with httpx.AsyncClient() as client:
                response = await client.get(feed_url)
            xml_content = response.text
            feed_cache[feed_url] = (current_time, xml_content)

        root = ET.fromstring(xml_content)
        raw_articles = root.findall('.//item') or root.findall('.//entry')
    except:
        raise HTTPException(status_code=500, detail="Error parsing XML")

    # searches XML for tags
    def get_text(elem, tags):
        for tag in tags:
            el = item.find(tag)
            if el is not None:
                return el.text
        return None

    for item in raw_articles:
        title = get_text(item, ['title'])
        url = get_text(item, ['link'])
        description = get_text(item, ['description', 'content'])
        date_str = get_text(item, ['pubDate', 'published', 'updated'])
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


@app.get('/all_articles')
async def get_all_articles(page_num: int, items_per_page: int):
    """
    Get items from all feeds, paginated.

    Args:
        page_num (int): The page number to retrieve (zero-indexed)
        items_per_page (int): The number of items per page

    Returns:
        dict{items, total_pages}: The items and total number of pages
    """
    global embeddings_trained

    try:
        lookup = db.sql('SELECT * FROM feeds').fetchall()
        feeds = [{'id': feed[0], 'url': feed[1], 'name': feed[2]} for feed in lookup]

        await asyncio.gather(*(
            parse_feed(feed['url'], feed['name']) for feed in feeds
        ))

        all_articles = db.sql("""
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
        """).fetchall()

        # duckdb gives list(tuple(json string)); parse it
        all_articles = [json.loads(article[0]) for article in all_articles]
        parsed_articles = []

        trained_svm = fit_svm(model, all_articles)

        for article in all_articles:
            if trained_svm:
                embeddings = model.embed([article['description']])
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

        return {
            # TODO: can make better
            'items': sorted(parsed_articles[start_idx:end_idx], key=lambda x: (-x['svm_prob'], -datetime.fromisoformat(x['date'] or '1900-01-01').timestamp())),
            'total_pages': len(parsed_articles) // items_per_page
        }
    except Exception as e:
        raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/create_feed')
async def create_feed(feed_url: str, feed_name: str):
    try:
        db.execute("""
            INSERT INTO feeds (id, url, name) 
            VALUES (nextval('feed_id_seq'), ?, ?)
        """, [feed_url, feed_name])

        await parse_feed(feed_url, feed_name) # update articles table
        return {"message": "Feed created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete('/delete_feed/{feed_url:path}')
async def delete_feed(feed_url: str):
    try:
        db.execute("DELETE FROM feeds WHERE url = ?", [feed_url])
        db.execute("DELETE FROM articles WHERE feed_url = ?", [feed_url])

        if feed_url in feed_cache:
            del feed_cache[feed_url]
        return {"message": "Feed deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/toggle_like_article')
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