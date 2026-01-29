import json
import os
from .storage import get_storage

class PortfolioManager:
    def __init__(self, data_file='data/portfolio.json'):
        self.storage = get_storage(data_file)
        # Ensure initial structure if empty
        data = self.load_data()
        if not data.get("holdings") and not data.get("watchlist"):
             self.ensure_initial_data()

    def ensure_initial_data(self):
         initial_data = {
            "holdings": [],
            "watchlist": [],
            "groups": [{"id": "default", "name": "默认分组"}]
         }
         self.save_data(initial_data)

    def load_data(self):
        """Load portfolio data from storage."""
        data = self.storage.load()
        if not data:
            return {
                "holdings": [], 
                "watchlist": [],
                "groups": [{"id": "default", "name": "默认分组"}]
            }
            
        # Migration: Ensure groups exist
        if "groups" not in data:
            data["groups"] = [{"id": "default", "name": "默认分组"}]
        
        # Always ensure holdings have group_id
        migrated = False
        for h in data.get("holdings", []):
            if "group_id" not in h:
                h["group_id"] = "default"
                migrated = True
        
        if migrated: 
            self.save_data(data)
            
        return data

    def save_data(self, data):
        """Save portfolio data to storage."""
        self.storage.save(data)

    def get_holdings(self):
        return self.load_data().get("holdings", [])
        
    def get_groups(self):
        return self.load_data().get("groups", [])

    def get_watchlist(self):
        return self.load_data().get("watchlist", [])

    def add_group(self, name):
        data = self.load_data()
        import uuid
        group_id = str(uuid.uuid4())
        data["groups"].append({"id": group_id, "name": name})
        self.save_data(data)
        return group_id

    def rename_group(self, group_id, new_name):
        data = self.load_data()
        for g in data["groups"]:
            if g["id"] == group_id:
                g["name"] = new_name
                self.save_data(data)
                return True
        return False

    def delete_group(self, group_id):
        if group_id == 'default':
            return False # Cannot delete default
        
        data = self.load_data()
        # Remove group
        data["groups"] = [g for g in data["groups"] if g["id"] != group_id]
        
        # Move items to default
        for h in data["holdings"]:
            if h.get("group_id") == group_id:
                h["group_id"] = "default"
                
        self.save_data(data)
        return True
        
    def reorder_groups(self, group_ids):
        data = self.load_data()
        # Sort groups based on the provided ID list order
        # group_ids is a list of ids in desired order
        
        # Create a map for current groups
        group_map = {g["id"]: g for g in data["groups"]}
        
        new_groups = []
        for gid in group_ids:
            if gid in group_map:
                new_groups.append(group_map[gid])
                
        # Append any groups that were missing in the input list (safety)
        existing_ids = set(group_ids)
        for g in data["groups"]:
            if g["id"] not in existing_ids:
                new_groups.append(g)
                
        data["groups"] = new_groups
        self.save_data(data)
        return True

    def add_holding(self, ticker, shares, cost, group_id='default', note=None):
        data = self.load_data()
        # Check if already exists, update if so
        found = False
        
        # Normalize target ticker base (remove suffix for loose comparison)
        target_base = ticker.split('.')[0]
        
        for item in data["holdings"]:
            current_ticker = item["ticker"]
            current_base = current_ticker.split('.')[0]
            
            # Match exact ticker OR base ticker (handling normalization migration)
            if current_ticker == ticker or current_base == target_base:
                item["ticker"] = ticker # Update to normalized ticker
                item["shares"] = shares
                item["cost"] = cost
                # Only update group if explicitly provided/changed? 
                # For now, let's assume we update it if provided, or keep existing if not?
                # Usually add/edit modal might pass group_id. 
                if group_id:
                    item["group_id"] = group_id
                elif "group_id" not in item:
                    item["group_id"] = "default"
                
                if note is not None:
                    item["note"] = note
                    
                found = True
                break
        
        if not found:
            data["holdings"].append({
                "ticker": ticker,
                "shares": shares,
                "cost": cost,
                "group_id": group_id or "default",
                "note": note or ""
            })
        
        self.save_data(data)
        return True

    def move_holding(self, ticker, target_group_id):
        data = self.load_data()
        target_base = ticker.split('.')[0]
        print(f"DEBUG: Manager moving {ticker} (base: {target_base}) to {target_group_id}")
        for item in data["holdings"]:
            current_ticker = item["ticker"]
            current_base = current_ticker.split('.')[0]
            if current_ticker == ticker or current_base == target_base:
                print(f"DEBUG: Found match {current_ticker}, updating group_id to {target_group_id}")
                item["group_id"] = target_group_id
                self.save_data(data)
                return True
        print("DEBUG: No match found in holdings")
        return False

    def remove_holding(self, ticker):
        data = self.load_data()
        # Remove by exact match or base match
        target_base = ticker.split('.')[0]
        data["holdings"] = [
            h for h in data["holdings"] 
            if h["ticker"] != ticker and h["ticker"].split('.')[0] != target_base
        ]
        self.save_data(data)
        return True

    def add_to_watchlist(self, ticker):
        data = self.load_data()
        if ticker not in data["watchlist"]:
            data["watchlist"].append(ticker)
            self.save_data(data)
        return True

    def remove_from_watchlist(self, ticker):
        data = self.load_data()
        if ticker in data["watchlist"]:
            data["watchlist"].remove(ticker)
            self.save_data(data)
        return True
