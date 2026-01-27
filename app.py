from flask import Flask, render_template, jsonify, request
from investment_master.core import InvestmentMaster
import traceback
import requests

app = Flask(__name__)
master = InvestmentMaster()

# Translation Dictionaries
SECTOR_MAP = {
    "Financial Services": "金融服务",
    "Technology": "科技",
    "Consumer Cyclical": "周期性消费",
    "Consumer Defensive": "防御性消费",
    "Healthcare": "医疗保健",
    "Industrials": "工业",
    "Energy": "能源",
    "Basic Materials": "基础材料",
    "Real Estate": "房地产",
    "Utilities": "公用事业",
    "Communication Services": "通信服务"
}

INDUSTRY_MAP = {
    "Banks - Regional": "区域性银行",
    "Banks - Diversified": "综合性银行",
    "Beverages - Wineries & Distilleries": "白酒/酿酒",
    "Electronic Components": "电子元件",
    "Semiconductors": "半导体",
    "Internet Content & Information": "互联网内容与信息",
    "Insurance - Life": "人寿保险",
    "Insurance - Property & Casualty": "财产保险",
    "Household Appliances": "家用电器",
    "Auto Parts": "汽车零部件",
    "Auto Manufacturers": "汽车制造"
}

def get_cn_stock_info(ticker):
    """
    Fetch Chinese name from Sina Finance API for A-shares
    """
    try:
        # Convert Ticker format: 600036.SS -> sh600036
        sina_code = ""
        if ticker.endswith('.SS'):
            sina_code = "sh" + ticker.split('.')[0]
        elif ticker.endswith('.SZ'):
            sina_code = "sz" + ticker.split('.')[0]
        else:
            return None # Not A-share or unknown
            
        url = f"http://hq.sinajs.cn/list={sina_code}"
        headers = {'Referer': 'https://finance.sina.com.cn'}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            content = response.text
            # Format: var hq_str_sh600036="招商银行,..."
            if '="' in content:
                data_str = content.split('="')[1]
                data_parts = data_str.split(',')
                if len(data_parts) > 1:
                    return {
                        "name": data_parts[0]
                    }
    except Exception as e:
        print(f"Error fetching CN info for {ticker}: {e}")
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze/<ticker>')
def analyze_stock(ticker):
    try:
        # 1. Normalize Ticker
        normalized_ticker = master._normalize_ticker(ticker)
        
        # 2. Get Basic Info & PE
        pe_data = master.valuator.calculate_pe(normalized_ticker)
        current_price = master.valuator.get_current_price(normalized_ticker)
        
        # 3. Valuation Models
        # Need to pass 'info' if possible to save API calls, but calculate_pb_roe fetches it internally if not provided.
        # Let's optimize slightly by fetching info once if we can, but for now let's stick to the methods.
        
        # We can try to get the 'info' dictionary from yfinance once to share, 
        # but the current Valuator methods might not all accept it.
        # calculate_pb_roe accepts info. calculate_pr accepts info.
        
        import yfinance as yf
        stock = yf.Ticker(normalized_ticker)
        try:
            info = stock.info
        except:
            info = {}

        pb_data = master.valuator.calculate_pb_roe(normalized_ticker, info=info)
        pr_data = master.valuator.calculate_pr(normalized_ticker, info=info)
        dcf_data = master.valuator.calculate_dcf(normalized_ticker) # Assuming signature
        graham_data = master.valuator.calculate_graham(normalized_ticker, info=info)
        peg_data = master.valuator.calculate_peg(normalized_ticker, info=info)
        ddm_data = master.valuator.calculate_ddm(normalized_ticker, info=info)
        tang_data = master.valuator.calculate_tang(normalized_ticker, info=info)
        
        # Determine Name and Translations
        cn_info = get_cn_stock_info(normalized_ticker)
        
        display_name = info.get('longName') or info.get('shortName') or normalized_ticker
        if cn_info and cn_info.get('name'):
            display_name = cn_info['name']
            
        raw_sector = info.get('sector', 'Unknown')
        raw_industry = info.get('industry', 'Unknown')
        
        display_sector = SECTOR_MAP.get(raw_sector, raw_sector)
        display_industry = INDUSTRY_MAP.get(raw_industry, raw_industry)

        result = {
            "ticker": normalized_ticker,
            "price": current_price,
            "name": display_name,
            "sector": display_sector,
            "industry": display_industry,
            "pe_data": pe_data,
            "pb_data": pb_data,
            "pr_data": pr_data,
            "dcf_data": dcf_data,
            "graham_data": graham_data,
            "peg_data": peg_data,
            "ddm_data": ddm_data,
            "tang_data": tang_data
        }
        
        return jsonify(result)
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/selection', methods=['POST'])
def run_selection():
    try:
        criteria = request.json or {}
        # Use default criteria if not provided or empty
        final_criteria = {
            'min_pe': float(criteria.get('min_pe', 0)),
            'max_pe': float(criteria.get('max_pe', 50)),
            'min_roe': float(criteria.get('min_roe', 15))
        }
        
        # For demo purposes, we might want to scan a fixed list or let user provide tickers
        # Since scanning all stocks is slow, let's use a sample list if not provided
        sample_tickers = ["600519.SS", "600036.SS", "000858.SZ", "000651.SZ", "601318.SS", "002594.SZ"]
        
        # In a real app, we would have a database. Here we scan the sample list.
        results = master.selector.select(final_criteria, sample_tickers)
        
        return jsonify({"results": results})
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/market_status')
def market_status():
    """
    Returns simulated sector performance data for the heatmap
    """
    import random
    
    sectors = [
        {"name": "银行", "change": 2.45, "heat": 0.8},
        {"name": "家用电器", "change": 1.82, "heat": 0.7},
        {"name": "食品饮料", "change": 1.25, "heat": 0.6},
        {"name": "煤炭", "change": 0.85, "heat": 0.5},
        {"name": "公用事业", "change": 0.52, "heat": 0.4},
        {"name": "交通运输", "change": -0.15, "heat": -0.1},
        {"name": "医药生物", "change": -0.45, "heat": -0.3},
        {"name": "电子", "change": -0.88, "heat": -0.5},
        {"name": "房地产", "change": -1.25, "heat": -0.7},
        {"name": "计算机", "change": -2.10, "heat": -0.9}
    ]
    
    # Optional: Randomize slightly for dynamic effect
    for s in sectors:
        noise = random.uniform(-0.2, 0.2)
        s["change"] = round(s["change"] + noise, 2)
    
    # Sort by change descending
    sectors.sort(key=lambda x: x["change"], reverse=True)
    
    return jsonify({"sectors": sectors})

# --- Portfolio API ---

@app.route('/api/portfolio/holdings', methods=['GET'])
def get_holdings():
    holdings = master.portfolio.get_holdings()
    # Enrich with current market data
    enriched_holdings = []
    for h in holdings:
        raw_ticker = h['ticker']
        # Normalize ticker for API calls (e.g. 513180 -> 513180.SS)
        ticker = master._normalize_ticker(raw_ticker)
        
        try:
            if ticker == 'CASH':
                current_price = 1.0
                name = '现金 (CNY)'
                market_value = h['shares'] # For Cash, shares stores the amount
                cost_basis = h['cost']
                # Usually cash gain is 0 unless tracking currency. 
                # Or user might input cost as original deposit amount and shares as current balance.
                # Let's assume shares = current balance, cost = original principle.
                gain = market_value - cost_basis
                gain_percent = (gain / cost_basis) * 100 if cost_basis > 0 else 0
                
                enriched_holdings.append({
                    "ticker": "CASH",
                    "name": name,
                    "shares": h['shares'],
                    "cost": h['cost'],
                    "current_price": 1.0,
                    "market_value": round(market_value, 2),
                    "gain": round(gain, 2),
                    "gain_percent": round(gain_percent, 2),
                    "group_id": h.get("group_id", "default")
                })
                continue

            current_price = master.valuator.get_current_price(ticker)
            cn_info = get_cn_stock_info(ticker)
            name = cn_info['name'] if cn_info else raw_ticker
            
            if current_price is not None:
                # Calculate market value and gain
                market_value = current_price * h['shares']
                cost_basis = h['cost'] * h['shares']
                gain = market_value - cost_basis
                gain_percent = (gain / cost_basis) * 100 if cost_basis > 0 else 0
                
                enriched_holdings.append({
                    "ticker": raw_ticker, # Keep original ticker for display/id consistency
                    "name": name,
                    "shares": h['shares'],
                    "cost": h['cost'],
                    "current_price": current_price,
                    "market_value": round(market_value, 2),
                    "gain": round(gain, 2),
                    "gain_percent": round(gain_percent, 2),
                    "group_id": h.get("group_id", "default")
                })
            else:
                # Price fetch failed
                enriched_holdings.append({
                    **h,
                    "name": name,
                    "current_price": "N/A",
                    "market_value": 0,
                    "gain": 0,
                    "gain_percent": 0,
                    "group_id": h.get("group_id", "default")
                })

        except Exception as e:
            print(f"Error enriching holding {raw_ticker}: {e}")
            enriched_holdings.append(h) # Return basic data if fetch fails
            
    return jsonify(enriched_holdings)

@app.route('/api/portfolio/groups', methods=['GET'])
def get_groups():
    return jsonify(master.portfolio.get_groups())

@app.route('/api/portfolio/groups', methods=['POST'])
def add_group():
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({"error": "Name is required"}), 400
    group_id = master.portfolio.add_group(name)
    return jsonify({"status": "success", "id": group_id})

@app.route('/api/portfolio/groups/<group_id>', methods=['PUT'])
def update_group(group_id):
    data = request.json
    new_name = data.get('name')
    if master.portfolio.rename_group(group_id, new_name):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to rename group"}), 500

@app.route('/api/portfolio/groups/<group_id>', methods=['DELETE'])
def delete_group(group_id):
    if master.portfolio.delete_group(group_id):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to delete group (cannot delete default or not found)"}), 400

@app.route('/api/portfolio/holdings/move', methods=['POST'])
def move_holding():
    data = request.json
    ticker = data.get('ticker')
    target_group_id = data.get('target_group_id')
    print(f"DEBUG: Move request - Ticker: {ticker}, Target Group: {target_group_id}")
    if master.portfolio.move_holding(ticker, target_group_id):
        print("DEBUG: Move success")
        return jsonify({"status": "success"})
    print("DEBUG: Move failed in manager")
    return jsonify({"error": "Failed to move holding"}), 500

@app.route('/api/portfolio/holdings', methods=['POST'])
def add_holding():
    data = request.json
    ticker = master._normalize_ticker(data.get('ticker'))
    shares = float(data.get('shares', 0))
    cost = float(data.get('cost', 0))
    group_id = data.get('group_id', 'default')
    
    if master.portfolio.add_holding(ticker, shares, cost, group_id):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to add holding"}), 500

@app.route('/api/portfolio/holdings/<ticker>', methods=['PUT'])
def update_holding(ticker):
    data = request.json
    # Ticker in URL is authoritative, but we normalize it just in case
    normalized_ticker = master._normalize_ticker(ticker)
    
    shares = float(data.get('shares', 0))
    cost = float(data.get('cost', 0))
    group_id = data.get('group_id')
    
    if master.portfolio.add_holding(normalized_ticker, shares, cost, group_id):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to update holding"}), 500

@app.route('/api/portfolio/holdings/<ticker>', methods=['DELETE'])
def remove_holding(ticker):
    if master.portfolio.remove_holding(ticker):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to remove holding"}), 500

@app.route('/api/portfolio/watchlist', methods=['GET'])
def get_watchlist():
    watchlist = master.portfolio.get_watchlist()
    enriched_watchlist = []
    for raw_ticker in watchlist:
        # Normalize ticker for API calls
        ticker = master._normalize_ticker(raw_ticker)
        try:
            # We need PE, Dividend, Change
            pe_data = master.valuator.calculate_pe(ticker)
            current_price = master.valuator.get_current_price(ticker)
            cn_info = get_cn_stock_info(ticker)
            name = cn_info['name'] if cn_info else raw_ticker
            
            # Safe access to pe_data which might be None
            if pe_data is None:
                pe_data = {}

            enriched_watchlist.append({
                "ticker": raw_ticker,
                "name": name,
                "price": current_price if current_price is not None else "N/A",
                "pe": pe_data.get('trailing_pe', '--'),
                "dividend_yield": pe_data.get('dividend_yield', 0),
                "change_percent": pe_data.get('change_percent', 0)
            })
        except Exception as e:
            print(f"Error enriching watchlist {raw_ticker}: {e}")
            enriched_watchlist.append({"ticker": raw_ticker})
            
    return jsonify(enriched_watchlist)

@app.route('/api/portfolio/watchlist', methods=['POST'])
def add_watchlist():
    data = request.json
    ticker = master._normalize_ticker(data.get('ticker'))
    if master.portfolio.add_to_watchlist(ticker):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to add to watchlist"}), 500

@app.route('/api/portfolio/watchlist/<ticker>', methods=['DELETE'])
def remove_watchlist(ticker):
    if master.portfolio.remove_from_watchlist(ticker):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to remove from watchlist"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
