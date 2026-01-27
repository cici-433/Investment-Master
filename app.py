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
            "dcf_data": dcf_data
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
