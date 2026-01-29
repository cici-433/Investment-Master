import json
import os
from pymongo import MongoClient

class StorageBackend:
    def load(self):
        raise NotImplementedError
    
    def save(self, data):
        raise NotImplementedError

class JsonFileStorage(StorageBackend):
    def __init__(self, file_path):
        self.file_path = file_path
        self._ensure_file()
        
    def _ensure_file(self):
        directory = os.path.dirname(self.file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        if not os.path.exists(self.file_path):
            self.save({}) # Init empty dict

    def load(self):
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading JSON from {self.file_path}: {e}")
            return {}

    def save(self, data):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving JSON to {self.file_path}: {e}")

class MongoStorage(StorageBackend):
    def __init__(self, uri, db_name, collection_name):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        
    def load(self):
        try:
            # We store the whole JSON blob as a single document with _id='data'
            # This is the simplest migration from file-based without refactoring everything
            doc = self.collection.find_one({"_id": "root_data"})
            if doc:
                return doc.get("data", {})
            return {}
        except Exception as e:
            print(f"Error loading from Mongo: {e}")
            return {}

    def save(self, data):
        try:
            self.collection.update_one(
                {"_id": "root_data"},
                {"$set": {"data": data}},
                upsert=True
            )
        except Exception as e:
            print(f"Error saving to Mongo: {e}")

def get_storage(file_path):
    mongo_uri = os.environ.get("MONGO_URI")
    if mongo_uri:
        # Infer collection name from filename
        # e.g., data/portfolio.json -> portfolio
        filename = os.path.basename(file_path)
        collection_name = filename.replace('.json', '')
        print(f"Using MongoDB Storage for {collection_name}")
        return MongoStorage(mongo_uri, "investment_master", collection_name)
    else:
        print(f"Using File Storage for {file_path}")
        return JsonFileStorage(file_path)
