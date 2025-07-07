import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from svm import SVMModel, fit_svm
from utils import ARTICLE_REFRESH_INTERVAL, MAX_ARTICLES, LOG_FILE, setup_db, parse_all_feeds

db = setup_db()
model = SVMModel()
parsed_articles = []


# ================================================
# HELPER METHODS
# ================================================

def load_article_table():
    """
    Helper method for refresh_articles
    Gets all article data (except liked status, for caching reasons)

    Returns:
        list[tuple]: The list of articles (tuple format)
    """
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
        WHERE feed_url IN (SELECT url FROM feeds WHERE is_visible = TRUE)
        ORDER BY COALESCE(date, '1900-01-01') DESC
        LIMIT ?
    """, [MAX_ARTICLES]).fetchall()
    all_articles = [json.loads(article[0]) for article in all_articles]

    return all_articles


def load_liked_articles():
    """
    Returns the list of liked articles
    """
    return {
        article[0]
        for article in db.execute("SELECT url FROM articles WHERE is_liked = true").fetchall()
    }


async def refresh_parsed_articles():
    """
    Refreshes the articles table in the DB with new articles from all feeds
    Also refits the SVM model

    Returns:
        list[dict]: The list of articles (dictionary format)
    """
    global parsed_articles

    await parse_all_feeds(db)
    all_articles = load_article_table()
    liked_urls = load_liked_articles()
    svm_is_trained = fit_svm(model, db)

    parsed_articles = []
    for article in all_articles:
        # we need something to embed
        if svm_is_trained and (article['description'] or article['title']):
            embeddings = model.embed([
                (article['description'] or '') + ' ' + (article['title'] or '')
            ])
            embeddings = np.array(embeddings)
            svm_prob = model.predict(embeddings)
        else:
            svm_prob = 0.5 # ambivalent

        # update liked status
        article['is_liked'] = article['url'] in liked_urls

        parsed_articles.append({
            **article,
            'svm_prob': svm_prob
        })

    return parsed_articles


async def auto_feed_refresh():
    """
    Refreshes the feeds and trains the SVM in regular intervals
    """
    global parsed_articles

    mins_to_sleep = 60
    while True:
        parsed_articles = await refresh_parsed_articles()
        await asyncio.sleep(60 * mins_to_sleep)


# ================================================
# FASTAPI SETUP
# ================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Speeds up startup time by pre-loading the database
    """
    asyncio.create_task(auto_feed_refresh())

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
# ROUTES
# ================================================
@app.get('/api/get_feeds')
async def get_feeds():
    """
    Get all feeds.

    Returns:
        list[(id, url, name, timestamp, is_visible)]: The list of RSS feeds
    """
    try:
        return db.sql('SELECT * FROM feeds').fetchall()
    except Exception as e:
        with open(LOG_FILE, 'a') as f:
            f.write(f'{datetime.now()} - {str(e)}\n')
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/articles')
async def get_articles(page_num: int, items_per_page: int, refresh: bool):
    """
    Get items from all feeds, paginated.

    Args:
        page_num (int): The page number to retrieve (zero-indexed)
        items_per_page (int): The number of items per page

    Returns:
        dict(items, total_pages): The items and total number of pages
    """
    global parsed_articles

    try:
        # force refresh everything
        if refresh:
            parsed_articles = await refresh_parsed_articles()

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
        with open(LOG_FILE, 'a') as f:
            f.write(f'{datetime.now()} - {str(e)}\n')
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/create_feed')
async def create_feed(feed_url: str, feed_name: str):
    try:
        db.execute("""
            INSERT INTO feeds (id, url, name, timestamp) 
            VALUES (nextval('feed_id_seq'), ?, ?, ?)
        """, [feed_url, feed_name, datetime.min])

        parse_all_feeds(db) # run in background is ok

        return {"message": "Feed created successfully"}
    except Exception as e:
        with open(LOG_FILE, 'a') as f:
            f.write(f'{datetime.now()} - {str(e)}\n')
        raise HTTPException(status_code=500, detail=str(e))


@app.delete('/api/delete_feed/{feed_url:path}')
async def delete_feed(feed_url: str):
    try:
        db.execute("DELETE FROM feeds WHERE url = ?", [feed_url])
        db.execute("DELETE FROM articles WHERE feed_url = ?", [feed_url])
        await parse_all_feeds(db)

        return {"message": "Feed deleted successfully"}
    except Exception as e:
        with open(LOG_FILE, 'a') as f:
            f.write(f'{datetime.now()} - {str(e)}\n')
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/toggle_like_article')
async def toggle_like_article(url: str):
    """
    Toggles the liked status of an article
    Changes are immediately reflected in cache
    """
    global parsed_articles
    
    try:
        # Get current liked status
        current_status = db.execute("SELECT is_liked FROM articles WHERE url = ?", [url]).fetchone()
        if not current_status:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Toggle in database
        db.execute("UPDATE articles SET is_liked = NOT is_liked WHERE url = ?", [url])
        new_status = not current_status[0]
        
        # Update cache immediately
        for article in parsed_articles:
            if article['url'] == url:
                article['is_liked'] = new_status
                break

        return {"message": f"Like status toggled successfully for {url}", "new_status": new_status}
    except Exception as e:
        with open(LOG_FILE, 'a') as f:
            f.write(f'{datetime.now()} - {str(e)}\n')
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/toggle_feed_visibility')
async def toggle_feed_visibility(feed_url: str):
    """
    Toggles the visibility status of a feed
    """
    global parsed_articles
    
    try:
        db.execute("UPDATE feeds SET is_visible = NOT is_visible WHERE url = ?", [feed_url])
        
        # Refresh cache to immediately reflect visibility changes
        parsed_articles = await refresh_parsed_articles()

        return {"message": f"Visibility status toggled successfully for {feed_url}"}
    except Exception as e:
        with open(LOG_FILE, 'a') as f:
            f.write(f'{datetime.now()} - {str(e)}\n')
        raise HTTPException(status_code=500, detail=str(e))
