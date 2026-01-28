import json
import os
import uuid
import time

class SystemManager:
    def __init__(self, data_file='data/investment_system.json'):
        self.data_file = data_file
        self.ensure_data_file()

    def ensure_data_file(self):
        """Ensure the data file and directory exist."""
        directory = os.path.dirname(self.data_file)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        
        if not os.path.exists(self.data_file):
            initial_data = {
                "articles": []
            }
            self.save_data(initial_data)

    def load_data(self):
        """Load system data from JSON file."""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading system data: {e}")
            return {"articles": []}

    def save_data(self, data):
        """Save system data to JSON file."""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving system data: {e}")

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
