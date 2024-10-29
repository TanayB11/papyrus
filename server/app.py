# app.py
from datetime import datetime
from dateutil.parser import parse
from urllib.parse import quote
import xml.etree.ElementTree as ET

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import requests
import uvicorn

import duckdb
from cachetools import cached, TTLCache

app = FastAPI()
cache = TTLCache(maxsize=250, ttl=60*5) # 5 minutes

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = duckdb.connect('./data/papyrus.db')

# Create sequence if it doesn't exist
db.execute("""
    CREATE SEQUENCE IF NOT EXISTS feed_id_seq;
""")

# Create feeds table if it doesn't exist
db.execute("""
    CREATE TABLE IF NOT EXISTS feeds (
        id INTEGER PRIMARY KEY DEFAULT nextval('feed_id_seq'),
        url VARCHAR,
        name VARCHAR
    )
""")

@app.get('/proxy')
async def proxy(url: str):
    try:
        response = requests.get(url)
        return Response(content=response.text, media_type="application/xml")
    except:
        raise HTTPException(status_code=500, detail="Error fetching RSS feed")

@app.get('/get_feeds')
async def get_feeds():
    try:
        return db.sql('SELECT * FROM feeds').fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@cached(cache=cache)
def get_all_feed_items():
    # Get all feeds
    lookup = db.sql('SELECT * FROM feeds').fetchall()
    feeds = [{'id': feed[0], 'url': feed[1], 'name': feed[2]} for feed in lookup]

    all_items = []
    for feed in feeds:
        feed_id, url, feed_name = feed['id'], feed['url'], feed['name']
        
        response = requests.get(url) # get XML
        xml_content = response.text
        try:
            root = ET.fromstring(xml_content) # parsed XML
        except:
            raise HTTPException(status_code=500, detail="Error parsing XML")
        
        items = root.findall('.//item') or root.findall('.//entry')

        for item in items:
            # Extract data with namespace handling
            def get_text(elem, tags):
                for tag in tags:
                    # Try without namespace
                    el = item.find(tag)
                    if el is not None:
                        return el.text
                return None

            # Get title and link
            title = get_text(item, ['title'])
            link = get_text(item, ['link'])
            
            # Get content/description
            description = get_text(item, ['description', 'content'])
            summary = get_text(item, ['summary'])
            
            # Get and parse date
            date_str = get_text(item, ['pubDate', 'published', 'updated'])
            try:
                date = parse(date_str) if date_str else None
            except:
                date = None
            
            if title and link:  # Only add if we have at least title and link
                all_items.append({
                    'feed_name': feed_name,
                    'title': title,
                    'link': link, 
                    'description': description,
                    'summary': summary,
                    'date': date.strftime('%Y-%m-%d') if date else None
                })
    
    all_items.sort(key=lambda x: x['date'] if x['date'] else datetime.min, reverse=True)
    return all_items


@app.get('/get_feed_items')
async def get_feed_items(page_num: int, items_per_page: int):
    # page_num is 0-indexed
    try:
        all_items = get_all_feed_items()
        
        # Calculate pagination
        start_idx = page_num * items_per_page
        end_idx = start_idx + items_per_page

        return {
            'items': all_items[start_idx:end_idx],
            'total_pages': len(all_items) // items_per_page
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/create_feed')
async def create_feed(feed_url: str, feed_name: str):
    try:
        print(feed_url, feed_name)
        db.execute("""
            INSERT INTO feeds (id, url, name) 
            VALUES (nextval('feed_id_seq'), ?, ?)
        """, [feed_url, feed_name])
        return {"message": "Feed created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete('/delete_feed/{feed_id}')
async def delete_feed(feed_id: int):
    try:
        db.execute("DELETE FROM feeds WHERE id = ?", [feed_id])
        return {"message": "Feed deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=3000)
