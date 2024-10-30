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

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cache = {} # key: feed_url, value: parsed_articles
CACHE_TTL = timedelta(minutes=2)

# ================================================
# DATABASE SETUP
# ================================================

db = duckdb.connect('./data/papyrus.db')

db.execute("""
    CREATE SEQUENCE IF NOT EXISTS feed_id_seq;
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS feeds (
        id INTEGER PRIMARY KEY DEFAULT nextval('feed_id_seq'),
        url VARCHAR,
        name VARCHAR
    )
""")

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


# @cached(cache=cache)
async def parse_feed(feed_url: str, feed_name: str):
    """
    Get articles from a feed.

    Args:
        feed_url (str): The URL of the feed
        feed_name (str): The nickname of the feed

    Returns:
        list[{ feed_name, title, link, description, summary, date }]: The list of parsed articles
    """
    parsed_articles = []

    # TODO: utilize cache

    try: # get and parse xml
        async with httpx.AsyncClient() as client:
            current_time = datetime.now()
            response = None

            if feed_url in cache:
                timestamp, response = cache[feed_url]
                if current_time - timestamp >= CACHE_TTL:
                    cache.pop(feed_url)
                    response = None
            if response is None:
                response = await client.get(feed_url)
                cache[feed_url] = (current_time, response)
            
        xml_content = response.text
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
        link = get_text(item, ['link'])
        description = get_text(item, ['description', 'content'])
        summary = get_text(item, ['summary'])
        date_str = get_text(item, ['pubDate', 'published', 'updated'])

        try:
            date = parse(date_str) if date_str else None
        except:
            date = None

        if title and link:
            parsed_articles.append({
                'feed_name': feed_name,
                'title': title,
                'link': link, 
                'description': description,
                'summary': summary,
                'date': date.strftime('%Y-%m-%d') if date else None
            })

    return parsed_articles


@app.get('/all_articles')
async def get_all_articles(page_num: int, items_per_page: int):
    """
    Get items from all feeds, paginated.

    Args:
        page_num (int): The current page number (zero-indexed)
        items_per_page (int): The number of items per page

    Returns:
        dict{items, total_pages}: The items and total number of pages
    """
    try:
        lookup = db.sql('SELECT * FROM feeds').fetchall()
        feeds = [{'id': feed[0], 'url': feed[1], 'name': feed[2]} for feed in lookup]

        results = await asyncio.gather(*(
            parse_feed(feed['url'], feed['name']) for feed in feeds
        ))

        all_articles = []
        for items in results:
            all_articles.extend(items)
        all_articles.sort(key=lambda x: x['date'] if x['date'] else datetime.min, reverse=True)
        
        # calculate pagination
        start_idx = page_num * items_per_page
        end_idx = start_idx + items_per_page

        return {
            'items': all_articles[start_idx:end_idx],
            'total_pages': len(all_articles) // items_per_page
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/create_feed')
async def create_feed(feed_url: str, feed_name: str):
    """
    Create a new feed.

    Args:
        feed_url (str): The URL of the feed
        feed_name (str): The nickname of the feed
    """
    try:
        db.execute("""
            INSERT INTO feeds (id, url, name) 
            VALUES (nextval('feed_id_seq'), ?, ?)
        """, [feed_url, feed_name])
        return {"message": "Feed created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete('/delete_feed/{feed_id}')
async def delete_feed(feed_id: int):
    """
    Delete a feed.

    Args:
        feed_id (int): The ID of the feed
    """
    try:
        db.execute("DELETE FROM feeds WHERE id = ?", [feed_id])
        return {"message": "Feed deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    port = os.getenv('PORT', 2430)
    uvicorn.run(app, host="0.0.0.0", port=port)
