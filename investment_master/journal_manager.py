import json
import os
import uuid
import time
from datetime import datetime
from .storage import get_storage

class JournalManager:
    def __init__(self, data_file='data/investment_journal.json'):
        self.storage = get_storage(data_file)
        data = self.load_data()
        if not data.get("entries"):
             self.save_data({"entries": []})

    def load_data(self):
        """Load journal data from storage."""
        data = self.storage.load()
        if not data:
            return {"entries": []}
        return data

    def save_data(self, data):
        """Save journal data to storage."""
        self.storage.save(data)

    def get_entries(self, limit=None):
        data = self.load_data()
        entries = data.get("entries", [])
        # Sort by date descending (newest first)
        entries.sort(key=lambda x: x.get('date', ''), reverse=True)
        if limit:
            return entries[:limit]
        return entries

    def add_entry(self, entry_type, title, content, date=None, ticker=None, tags=None):
        data = self.load_data()
        
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
            
        entry = {
            "id": str(uuid.uuid4()),
            "type": entry_type, # 'trade', 'review', 'note', 'plan'
            "title": title,
            "content": content,
            "date": date,
            "ticker": ticker,
            "tags": tags or [],
            "created_at": int(time.time()),
            "updated_at": int(time.time())
        }
        
        data["entries"].append(entry)
        self.save_data(data)
        return entry

    def update_entry(self, entry_id, entry_type=None, title=None, content=None, date=None, ticker=None, tags=None):
        data = self.load_data()
        for entry in data["entries"]:
            if entry["id"] == entry_id:
                if entry_type: entry["type"] = entry_type
                if title: entry["title"] = title
                if content: entry["content"] = content
                if date: entry["date"] = date
                if ticker is not None: entry["ticker"] = ticker
                if tags is not None: entry["tags"] = tags
                entry["updated_at"] = int(time.time())
                self.save_data(data)
                return True
        return False

    def delete_entry(self, entry_id):
        data = self.load_data()
        original_count = len(data["entries"])
        data["entries"] = [e for e in data["entries"] if e["id"] != entry_id]
        if len(data["entries"]) < original_count:
            self.save_data(data)
            return True
        return False
