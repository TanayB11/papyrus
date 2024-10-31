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
from sklearn.svm import SVC
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import PCA

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

feed_cache = {} # key: feed_url, value: (timestamp, XML data)
CACHE_TTL = timedelta(minutes=1)


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
# TODO: NLP MODELING SETUP
# ================================================
tfidf = TfidfVectorizer()

MIN_DATASET_SIZE = 10

# get liked articles and equal number of random unliked articles for training
liked_articles = db.sql('SELECT title, description FROM articles WHERE is_liked = true').fetchall()
unliked_articles = db.sql(f'SELECT title, description FROM articles WHERE is_liked = false ORDER BY RANDOM() LIMIT {len(liked_articles)}').fetchall()
dataset = liked_articles + unliked_articles

# TODO: make code neater
print(len(dataset))
if len(dataset) >= MIN_DATASET_SIZE:
    # extract features from article descriptions
    # shape: (n_samples, n_features)
    X = tfidf.fit_transform([article[1] for article in dataset])

    # n_features is high; reduce dimensionality for SVM
    n_components = min(X.shape[0]-1, X.shape[1]-1, 100)
    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X)

    # create labels array (1 for liked, 0 for unliked)
    y = np.array([1] * len(liked_articles) + [0] * len(unliked_articles))

    # fit SVM classifier
    svm = SVC(kernel='rbf', probability=True)
    svm.fit(X_pca, y)


# EDA
# plot first 2 principal components
from matplotlib import pyplot as plt
plt.figure(figsize=(10, 6))
plt.scatter(X_pca[len(liked_articles):, 0], X_pca[len(liked_articles):, 1], label='Unliked', alpha=0.5)
plt.scatter(X_pca[:len(liked_articles), 0], X_pca[:len(liked_articles), 1], label='Liked', alpha=0.5)
plt.xlabel('First Principal Component')
plt.ylabel('Second Principal Component')
plt.title('PCA of Article Features')
plt.legend()
plt.savefig('pca_plot.png')
plt.close()


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
        async with httpx.AsyncClient() as client:
            current_time = datetime.now()
            xml_content = None

            if feed_url in feed_cache:
                timestamp, xml_content = feed_cache[feed_url]
                if current_time - timestamp < CACHE_TTL:
                    return # no need to repopulate the tables
                feed_cache.pop(feed_url)
                xml_content = None

            if xml_content is None:
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

        parsed_articles = []
        for article in all_articles:
            loaded_article = json.loads(article[0])

            if len(dataset) >= MIN_DATASET_SIZE:
                description = loaded_article['description']
                description_vector = tfidf.transform([description])
                description_pca = pca.transform(description_vector)
                svm_prob = svm.predict_proba(description_pca)[0][1]
            else:
                svm_prob = 0.5

            parsed_articles.append({
                **loaded_article,
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