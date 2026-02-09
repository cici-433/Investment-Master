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
        updated = False
        if not data.get("articles"):
             data["articles"] = []
             updated = True
        if not data.get("checklist"):
             data["checklist"] = {
                 "buy": [
                     {"id": "1", "text": "估值检查：当前价格是否低于合理估值？安全边际是否充足？", "required": True},
                     {"id": "2", "text": "逻辑检查：买入的核心逻辑（成长/低估/红利）是否清晰且成立？", "required": True},
                     {"id": "3", "text": "仓位检查：单票仓位是否控制在 15% 以内？", "required": True},
                     {"id": "4", "text": "情绪检查：是否处于非理性亢奋或恐慌状态？(避免 FOMO)", "required": True},
                     {"id": "5", "text": "计划检查：是否已设定好止损点或分批买入计划？", "required": True}
                 ],
                 "sell": [
                     {"id": "1", "text": "估值检查：价格是否严重高估（如PEG>1.5 / 历史高位）？", "required": True},
                     {"id": "2", "text": "逻辑检查：买入逻辑是否破坏？基本面是否恶化？", "required": True},
                     {"id": "3", "text": "机会成本：是否有更优质的标的替代？", "required": True},
                     {"id": "4", "text": "情绪检查：是否因短期波动恐慌而卖出？", "required": True},
                     {"id": "5", "text": "计划检查：是否达到止盈/止损目标？", "required": True}
                 ]
             }
             updated = True
        elif isinstance(data["checklist"], list):
            # Migration: Convert old list format to new dict format
            old_list = data["checklist"]
            data["checklist"] = {
                "buy": old_list,
                "sell": [
                     {"id": "1", "text": "估值检查：价格是否严重高估（如PEG>1.5 / 历史高位）？", "required": True},
                     {"id": "2", "text": "逻辑检查：买入逻辑是否破坏？基本面是否恶化？", "required": True},
                     {"id": "3", "text": "机会成本：是否有更优质的标的替代？", "required": True},
                     {"id": "4", "text": "情绪检查：是否因短期波动恐慌而卖出？", "required": True},
                     {"id": "5", "text": "计划检查：是否达到止盈/止损目标？", "required": True}
                 ]
            }
            updated = True
        
        if updated:
            self.save_data(data)

    def load_data(self):
        """Load system data from storage."""
        data = self.storage.load()
        if not data:
            return {"articles": [], "checklist": { "buy": [], "sell": [] }}
        return data

    def get_checklist(self, type='buy'):
        data = self.load_data()
        checklist = data.get("checklist")
        
        # Handle case where checklist might be a list (legacy data not yet migrated by init)
        if isinstance(checklist, list):
            if type == 'buy':
                return checklist
            return []
            
        if not checklist:
            return []
            
        return checklist.get(type, [])

    def update_checklist(self, items, type='buy'):
        data = self.load_data()
        if isinstance(data["checklist"], list):
            # Force migration if updating
            data["checklist"] = {"buy": data["checklist"], "sell": []}
            
        if not data.get("checklist"):
             data["checklist"] = {"buy": [], "sell": []}
             
        data["checklist"][type] = items
        self.save_data(data)
        return True

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
