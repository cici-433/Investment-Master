import json
import os

class PortfolioManager:
    def __init__(self, data_file='data/portfolio.json'):
        self.data_file = data_file
        self.ensure_data_file()

    def ensure_data_file(self):
        """Ensure the data file and directory exist."""
        directory = os.path.dirname(self.data_file)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        
        if not os.path.exists(self.data_file):
            initial_data = {
                "holdings": [],
                "watchlist": []
            }
            self.save_data(initial_data)

    def load_data(self):
        """Load portfolio data from JSON file."""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading portfolio data: {e}")
            return {"holdings": [], "watchlist": []}

    def save_data(self, data):
        """Save portfolio data to JSON file."""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving portfolio data: {e}")

    def get_holdings(self):
        return self.load_data().get("holdings", [])

    def get_watchlist(self):
        return self.load_data().get("watchlist", [])

    def add_holding(self, ticker, shares, cost):
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
                found = True
                break
        
        if not found:
            data["holdings"].append({
                "ticker": ticker,
                "shares": shares,
                "cost": cost
            })
        
        self.save_data(data)
        return True

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
