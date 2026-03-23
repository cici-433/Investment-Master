import json
import os
import re
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

    def _find_my_system_article(self, data):
        articles = data.get("articles", []) if isinstance(data, dict) else []
        for a in articles:
            if (a.get("title") or "").strip() == "我的投资体系":
                return a
        return None

    def _parse_system_decision_rules(self, markdown):
        if not markdown or not isinstance(markdown, str):
            return None

        sections = {
            "buy": {"items": [], "mode": None},
            "sell": {"items": [], "mode": None},
        }

        current = None
        current_level = None
        counters = {"buy": 0, "sell": 0}

        def set_mode(section, heading_text):
            if not heading_text:
                return
            t = heading_text.upper()
            if "ANY" in t or "任一" in heading_text or "任意" in heading_text:
                sections[section]["mode"] = "any"
                return
            if "ALL" in t or "全部" in heading_text:
                sections[section]["mode"] = "all"

        for raw in markdown.splitlines():
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped:
                continue

            m_head = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if m_head:
                level = len(m_head.group(1))
                title = m_head.group(2).strip()
                compact = title.replace(" ", "")
                if "买入" in compact:
                    current = "buy"
                    current_level = level
                    set_mode("buy", title)
                    continue
                if "卖出" in compact or "减仓" in compact:
                    current = "sell"
                    current_level = level
                    set_mode("sell", title)
                    continue
                if current and current_level is not None and level <= current_level:
                    current = None
                    current_level = None
                continue

            if not current:
                continue

            m_item = re.match(r"^\s*(?:[-*+]|(\d+)[.)])\s+(.*)$", line)
            if not m_item:
                continue

            text = (m_item.group(2) or "").strip()
            if not text:
                continue

            required = True
            for prefix in ("[可选]", "（可选）", "(可选)", "可选：", "可选:"):
                if text.startswith(prefix):
                    required = False
                    text = text[len(prefix):].strip()
                    break

            if not text:
                continue

            counters[current] += 1
            sections[current]["items"].append({
                "id": str(counters[current]),
                "text": text,
                "required": required
            })

        if sections["buy"]["items"] or sections["sell"]["items"]:
            if not sections["buy"]["mode"]:
                sections["buy"]["mode"] = "all"
            if not sections["sell"]["mode"]:
                sections["sell"]["mode"] = "all"
            return sections

        return None

    def get_checklist(self, type='buy'):
        data = self.load_data()
        article = self._find_my_system_article(data)
        if article:
            rules = self._parse_system_decision_rules(article.get("content") or "")
            if rules and type in rules:
                updated_at = article.get("updated_at") or article.get("created_at")
                return {
                    "items": rules[type]["items"],
                    "mode": rules[type].get("mode") or "all",
                    "source": "my_system",
                    "updated_at": updated_at
                }

        checklist = data.get("checklist")
        
        # Handle case where checklist might be a list (legacy data not yet migrated by init)
        if isinstance(checklist, list):
            if type == 'buy':
                return {"items": checklist, "mode": "all", "source": "checklist"}
            return {"items": [], "mode": "all", "source": "checklist"}
            
        if not checklist:
            return {"items": [], "mode": "all", "source": "checklist"}
            
        return {"items": checklist.get(type, []), "mode": "all", "source": "checklist"}

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
