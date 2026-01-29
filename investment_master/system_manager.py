import json
import os
import uuid
import time
from .storage import get_storage

class SystemManager:
    def __init__(self, data_file='data/investment_system.json'):
        self.storage = get_storage(data_file)
        # Ensure initial structure if empty
        data = self.load_data()
        if not data.get("articles"):
             self.save_data({"articles": []})

    def load_data(self):
        """Load system data from storage."""
        data = self.storage.load()
        if not data:
            return {"articles": []}
        return data

    def save_data(self, data):
        """Save system data to storage."""
        self.storage.save(data)

    def get_articles(self):
        return self.load_data().get("articles", [])

    def add_article(self, title, author, content, tags=None):
        data = self.load_data()
        article = {
            "id": str(uuid.uuid4()),
            "title": title,
            "author": author,
            "content": content,
            "tags": tags or [],
            "created_at": int(time.time())
        }
        data["articles"].append(article)
        self.save_data(data)
        return article

    def update_article(self, article_id, title=None, author=None, content=None, tags=None):
        data = self.load_data()
        for article in data["articles"]:
            if article["id"] == article_id:
                if title: article["title"] = title
                if author: article["author"] = author
                if content: article["content"] = content
                if tags is not None: article["tags"] = tags
                article["updated_at"] = int(time.time())
                self.save_data(data)
                return True
        return False

    def delete_article(self, article_id):
        data = self.load_data()
        original_count = len(data["articles"])
        data["articles"] = [a for a in data["articles"] if a["id"] != article_id]
        if len(data["articles"]) < original_count:
            self.save_data(data)
            return True
        return False
