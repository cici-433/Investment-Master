from flask import Flask, render_template, jsonify, request, Response, stream_with_context
from investment_master.core import InvestmentMaster
from investment_master.scraper import ArticleScraper
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
    Fetch Chinese name from Sina Finance API for A-shares.
    Fallback to local portfolio.json data if API fails.
    """
    cn_name = None
    day_change_percent = 0.0
    
    # 1. Try Sina API first
    try:
        # Convert Ticker format: 600036.SS -> sh600036
        sina_code = ""
        if ticker.endswith('.SS'):
            sina_code = "sh" + ticker.split('.')[0]
        elif ticker.endswith('.SZ'):
            sina_code = "sz" + ticker.split('.')[0]
        
        if sina_code:
            url = f"http://hq.sinajs.cn/list={sina_code}"
            headers = {'Referer': 'https://finance.sina.com.cn'}
            response = requests.get(url, headers=headers, timeout=2) # Short timeout
            
            if response.status_code == 200:
                content = response.text
                # Format: var hq_str_sh600036="招商银行,open,pre_close,current,high,low,..."
                if '="' in content:
                    data_str = content.split('="')[1]
                    data_parts = data_str.split(',')
                    if len(data_parts) > 3:
                        cn_name = data_parts[0]
                        pre_close = float(data_parts[2])
                        current = float(data_parts[3])
                        if pre_close > 0:
                            day_change_percent = (current - pre_close) / pre_close * 100
                        
                        return {
                            "name": cn_name,
                            "current_price": current,
                            "pre_close": pre_close,
                            "day_change_percent": day_change_percent
                        }
    except Exception as e:
        print(f"Error fetching CN info for {ticker} from Sina: {e}")

    # 2. Fallback to local portfolio data
    try:
        portfolio_data = master.portfolio.load_data()
        
        # Check holdings
        for h in portfolio_data.get('holdings', []):
            if h.get('ticker') == ticker and h.get('name'):
                return {
                    "name": h['name'],
                    # We can't get real-time price from local file, so return None for those
                    "current_price": None, 
                    "pre_close": None,
                    "day_change_percent": None
                }
                
        # Check watchlist
        for w in portfolio_data.get('watchlist', []):
            if isinstance(w, dict) and w.get('ticker') == ticker and w.get('name'):
                 return {
                    "name": w['name'],
                    "current_price": None,
                    "pre_close": None,
                    "day_change_percent": None
                }
    except Exception as e:
        print(f"Error fetching CN info from local file: {e}")

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

@app.route('/api/system/articles', methods=['GET'])
def get_articles():
    return jsonify(master.system_manager.get_articles())

@app.route('/api/system/articles', methods=['POST'])
def add_article():
    data = request.json
    title = data.get('title')
    author = data.get('author')
    content = data.get('content')
    tags = data.get('tags') # List of strings
    
    if not title:
        return jsonify({"error": "Title is required"}), 400
        
    article = master.system_manager.add_article(title, author, content, tags)
    return jsonify({"status": "success", "article": article})

@app.route('/api/reports')
def get_reports():
    ticker = request.args.get('ticker')
    if not ticker:
        return jsonify({"error": "Ticker is required"}), 400
    try:
        reports = master.report_manager.get_reports(ticker)
        return jsonify(reports)
    except Exception as e:
        print(f"Error getting reports: {e}")
        traceback.print_exc()
        return jsonify([])

@app.route('/api/system/scrape', methods=['POST'])
def scrape_article():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    scraper = ArticleScraper()
    result = scraper.scrape(url)
    
    if "error" in result:
        return jsonify({"error": result["error"]}), 500
        
    return jsonify(result)

@app.route('/api/system/articles/<article_id>', methods=['PUT'])
def update_article(article_id):
    data = request.json
    title = data.get('title')
    author = data.get('author')
    content = data.get('content')
    tags = data.get('tags')
    
    if master.system_manager.update_article(article_id, title, author, content, tags):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to update article"}), 500

@app.route('/api/system/articles/<article_id>', methods=['DELETE'])
def delete_article(article_id):
    if master.system_manager.delete_article(article_id):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to delete article"}), 500

# --- Journal API ---

@app.route('/api/journal/entries', methods=['GET'])
def get_journal_entries():
    return jsonify(master.journal_manager.get_entries())

@app.route('/api/journal/entries', methods=['POST'])
def add_journal_entry():
    data = request.json
    title = data.get('title')
    content = data.get('content')
    entry_type = data.get('type', 'note')
    date = data.get('date')
    ticker = data.get('ticker')
    tags = data.get('tags')
    
    if not title:
        return jsonify({"error": "Title is required"}), 400
        
    entry = master.journal_manager.add_entry(entry_type, title, content, date, ticker, tags)
    return jsonify({"status": "success", "entry": entry})

@app.route('/api/journal/entries/<entry_id>', methods=['PUT'])
def update_journal_entry(entry_id):
    data = request.json
    title = data.get('title')
    content = data.get('content')
    entry_type = data.get('type')
    date = data.get('date')
    ticker = data.get('ticker')
    tags = data.get('tags')
    
    if master.journal_manager.update_entry(entry_id, entry_type, title, content, date, ticker, tags):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to update entry"}), 500

@app.route('/api/journal/entries/<entry_id>', methods=['DELETE'])
def delete_journal_entry(entry_id):
    if master.journal_manager.delete_entry(entry_id):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to delete entry"}), 500

@app.route('/api/system/checklist', methods=['GET'])
def get_checklist():
    checklist_type = request.args.get('type', 'buy')
    return jsonify(master.system_manager.get_checklist(type=checklist_type))

@app.route('/api/system/checklist', methods=['POST'])
def update_checklist():
    data = request.json
    items = data.get('items')
    checklist_type = data.get('type', 'buy')
    
    if items is None:
         # Backward compatibility if user sends just the list (though frontend should be updated)
         # Assuming if it's a list, it's items. But request.json returns the body.
         if isinstance(data, list):
             items = data
    
    if master.system_manager.update_checklist(items, type=checklist_type):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to update checklist"}), 500

# --- AI Analysis Helper ---
def call_volcengine_api(prompt, use_search=True):
    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    api_key = "320f463e-3712-42e8-b7b7-b43c9e8e1e8b"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "glm-4-7-251222",
        "messages": [
            {
                "role": "system",
                "content": "You are a professional investment advisor."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False
    }

    if use_search:
        # Volcengine's standard chat/completions might not support the web_search tool format 
        # in the same way as the proprietary endpoint.
        # Disabling tools for now to ensure compatibility with the user-provided example.
        # payload["tools"] = [
        #     {
        #         "type": "web_search",
        #         "web_search": {
        #             "enable": True
        #         }
        #     }
        # ]
        pass
    
    try:
        # Increase timeout to 300s for deep analysis
        response = requests.post(url, headers=headers, json=payload, timeout=300)
        
        # Check for specific ToolNotOpen error in JSON even if status is 200 (sometimes APIs do that) or 400
        res_json = None
        try:
            res_json = response.json()
        except:
            pass

        if res_json and "error" in res_json:
            error_code = res_json["error"].get("code")
            # If tool error, retry without tools
            if (error_code == "ToolNotOpen" or error_code == "BadRequest") and use_search:
                print(f"Web search failed ({error_code}), retrying without tools...")
                return call_volcengine_api(prompt, use_search=False)
            return f"Error from AI API: {res_json['error'].get('message', res_json)}"

        if response.status_code == 200:
            if res_json and "choices" in res_json and len(res_json["choices"]) > 0:
                return res_json["choices"][0]["message"]["content"]
            else:
                return f"Error: Unexpected response format: {res_json}"
        else:
            return f"Error: API Request failed with status {response.status_code}: {response.text}"
            
    except Exception as e:
        return f"Error calling AI API: {str(e)}"

# --- Portfolio API ---

@app.route('/api/portfolio/analysis', methods=['GET'])
def get_portfolio_analysis():
    analysis = master.portfolio.get_last_analysis()
    return jsonify(analysis if analysis else {})

import threading

@app.route('/api/portfolio/analyze', methods=['POST'])
def analyze_portfolio():
    # Return immediately to avoid timeout
    master.portfolio.set_analysis_status("analyzing")
    
    def run_analysis():
        try:
            # 1. Gather Portfolio Data
            holdings = master.portfolio.get_holdings()
            
            portfolio_summary = []
            for h in holdings:
                ticker = h['ticker']
                
                # Enrich with price info
                price_info = "价格未知"
                try:
                    # Reuse get_cn_stock_info logic
                    info = get_cn_stock_info(ticker)
                    if info and info.get('current_price'):
                        price = info['current_price']
                        change = info.get('day_change_percent', 0)
                        price_info = f"现价 {price} (涨跌 {change:.2f}%)"
                    elif ticker == 'CASH':
                        price_info = "现金资产"
                except:
                    pass
                    
                portfolio_summary.append(f"- {h.get('name') or h['ticker']} ({h['ticker']}): {price_info}, 持仓 {h['shares']}股, 成本 {h['cost']}, 备注: {h.get('note', '')}")

            prompt = f"""
            请作为一位专业的投资顾问，帮我分析当前的持仓组合。
            **我的持仓列表:**
            {chr(10).join(portfolio_summary)}

            **请提供以下分析:**
            1. **组合健康度诊断**: 行业分布、风险敞口、是否存在过度集中？
            2. **个股深度点评**: 逐一分析主要持仓，判断高估/低估，是否有重大基本面问题？
            3. **改进建议与操作指南**: 买卖/加仓建议，市场环境应对策略。

            请用Markdown格式输出，保持客观、犀利。
            """

            # 2. Call AI
            ai_response = call_volcengine_api(prompt)
            
            if ai_response.startswith("Error"):
                 master.portfolio.save_analysis(ai_response, status="error")
            else:
                 # 3. Save Result
                 master.portfolio.save_analysis(ai_response, status="completed")
                 
        except Exception as e:
            print(f"Analysis thread error: {e}")
            master.portfolio.save_analysis(f"Analysis failed: {str(e)}", status="error")

    # Start background thread
    thread = threading.Thread(target=run_analysis)
    thread.start()
    
    return jsonify({
        "status": "accepted", 
        "message": "Analysis started in background",
        "timestamp": __import__('time').time()
    })

@app.route('/api/portfolio/holdings', methods=['GET'])
def get_holdings():
    holdings = master.portfolio.get_holdings()
    enriched_holdings = []
    for h in holdings:
        raw_ticker = h['ticker']
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
                    "day_change_percent": 0,
                    "group_id": h.get("group_id", "default"),
                    "note": h.get("note", "")
                })
                continue

            # Try to get info from Sina first (faster for A-shares)
            cn_info = get_cn_stock_info(ticker)
            day_change_percent = 0
            
            if cn_info:
                name = cn_info['name']
                current_price = cn_info.get('current_price')
                day_change_percent = cn_info.get('day_change_percent', 0)
                # Fallback to yfinance if Sina price is 0 (suspended or error)
                if current_price == 0:
                     current_price = master.valuator.get_current_price(ticker)
                     # Recalculate change percent if we have pre_close
                     if current_price and cn_info.get('pre_close') and cn_info['pre_close'] > 0:
                         day_change_percent = (current_price - cn_info['pre_close']) / cn_info['pre_close'] * 100
            else:
                name = raw_ticker
                current_price = master.valuator.get_current_price(ticker)
            
            if current_price is not None:
                # Calculate market value and gain
                market_value = current_price * h['shares']
                cost_basis = h['cost'] * h['shares']
                gain = market_value - cost_basis
                gain_percent = (gain / cost_basis) * 100 if cost_basis > 0 else 0
                
                # Calculate Day Gain
                day_gain = 0
                if cn_info and cn_info.get('pre_close'):
                     day_gain = (current_price - cn_info['pre_close']) * h['shares']
                elif day_change_percent != 0:
                     # Estimate if we only have percent (fallback)
                     pre_c = current_price / (1 + day_change_percent/100)
                     day_gain = (current_price - pre_c) * h['shares']

                enriched_holdings.append({
                    "ticker": raw_ticker, # Keep original ticker for display/id consistency
                    "name": name,
                    "shares": h['shares'],
                    "cost": h['cost'],
                    "current_price": current_price,
                    "market_value": round(market_value, 2),
                    "gain": round(gain, 2),
                    "gain_percent": round(gain_percent, 2),
                    "day_change_percent": round(day_change_percent, 2),
                    "day_gain": round(day_gain, 2),
                    "group_id": h.get("group_id", "default"),
                    "note": h.get("note", "")
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
                    "group_id": h.get("group_id", "default"),
                    "note": h.get("note", "")
                })

        except Exception as e:
            print(f"Error enriching holding {raw_ticker}: {e}")
            enriched_holdings.append(h) # Return basic data if fetch fails
            
    return jsonify(enriched_holdings)

@app.route('/api/portfolio/decision/<ticker>', methods=['GET'])
def get_holding_decision(ticker):
    if not ticker:
        return jsonify({}), 400
    decision = master.portfolio.get_decision(ticker)
    return jsonify(decision or {})

@app.route('/api/portfolio/decision/indicators', methods=['POST'])
def save_holding_decision_indicators():
    data = request.json or {}
    ticker = data.get('ticker')
    indicators = data.get('indicators', '')
    if not ticker:
        return jsonify({"status": "error", "error": "Ticker is required"}), 400
    master.portfolio.save_decision_indicators(ticker, indicators or '')
    return jsonify({"status": "success"})

@app.route('/api/portfolio/decision', methods=['POST'])
def holding_decision():
    data = request.json or {}
    ticker = data.get('ticker')
    if not ticker:
        return jsonify({"status": "error", "error": "Ticker is required"}), 400
    
    holdings = master.portfolio.get_holdings()
    base = ticker.split('.')[0]
    holding = None
    for h in holdings:
        ht = h.get('ticker')
        if not ht:
            continue
        hb = ht.split('.')[0]
        if ht == ticker or hb == base:
            holding = h
            break
    
    if not holding:
        return jsonify({"status": "error", "error": "Holding not found"}), 404
    
    normalized = master._normalize_ticker(holding['ticker'])
    name = holding.get('name')
    current_price = None
    pe_data = None
    pb_data = None
    cn_info = get_cn_stock_info(normalized)
    if cn_info and not name:
        name = cn_info.get('name')
    
    try:
        current_price = master.valuator.get_current_price(normalized)
        pe_data = master.valuator.calculate_pe(normalized)
        import yfinance as yf
        stock = yf.Ticker(normalized)
        try:
            info = stock.info
        except:
            info = {}
        pb_data = master.valuator.calculate_pb_roe(normalized, info=info)
    except Exception as e:
        print(f"Error in decision valuation for {normalized}: {e}")
    
    shares = holding.get('shares', 0)
    cost = holding.get('cost', 0)
    gain_text = ""
    if current_price is not None and shares and cost:
        market_value = current_price * shares
        cost_basis = cost * shares
        gain = market_value - cost_basis
        gain_percent = (gain / cost_basis) * 100 if cost_basis > 0 else 0
        gain_text = f"当前市值约 {round(market_value, 2)} 元，浮动盈亏 {round(gain, 2)} 元，收益率 {round(gain_percent, 2)}%。"
    
    valuation_lines = []
    if pe_data:
        tp = pe_data.get("trailing_pe")
        fp = pe_data.get("forward_pe")
        pb = pe_data.get("price_to_book")
        roe = pe_data.get("return_on_equity")
        dy = pe_data.get("dividend_yield")
        if tp:
            valuation_lines.append(f"TTM PE 约 {round(tp, 2)} 倍")
        if fp:
            valuation_lines.append(f"Forward PE 约 {round(fp, 2)} 倍")
        if pb:
            valuation_lines.append(f"PB 约 {round(pb, 2)} 倍")
        if roe:
            valuation_lines.append(f"ROE 约 {round(roe * 100, 2)}%")
        if dy:
            dy_val = dy
            if dy_val < 1:
                dy_val = dy_val * 100
            valuation_lines.append(f"股息率约 {round(dy_val, 2)}%")
    
    if pb_data and "error" not in pb_data:
        margin = pb_data.get("margin")
        fair_value = pb_data.get("fair_value")
        buy_range = pb_data.get("buy_range_price")
        sell_range = pb_data.get("sell_range_price")
        if fair_value is not None:
            valuation_lines.append(f"PB-ROE 模型合理价值约 {fair_value} 元/股")
        if margin is not None:
            valuation_lines.append(f"当前安全边际约 {margin}%")
        if isinstance(buy_range, (list, tuple)) and len(buy_range) == 2:
            valuation_lines.append(f"PB-ROE 模型建议买入区间约 {round(buy_range[0], 2)} - {round(buy_range[1], 2)} 元")
        if isinstance(sell_range, (list, tuple)) and len(sell_range) == 2:
            valuation_lines.append(f"PB-ROE 模型建议卖出区间约 {round(sell_range[0], 2)} - {round(sell_range[1], 2)} 元")
    
    valuation_summary = "暂无完整估值数据，可更多依赖你的观察指标。" 
    if valuation_lines:
        valuation_summary = "\n".join(f"- {line}" for line in valuation_lines)
    
    note_text = holding.get('note', '') or ''
    indicators = data.get('indicators', '')
    indicators_text = indicators.strip() if isinstance(indicators, str) else ""
    if not indicators_text:
        indicators_text = note_text
    
    prompt = f"""你是一个严格执行纪律的价值投资助手，请完全基于下面给出的“关键观察指标”和估值数据，给出当前这只股票的具体操作建议。

【标的基本信息】
- 名称: {name or '未知'}
- 代码: {normalized}
- 当前价格: {current_price if current_price is not None else '未知'} 元
- 持仓成本: {cost} 元
- 持仓数量: {shares} 股
{gain_text}

【估值与财务摘要】
{valuation_summary}

【关键观察指标与个人规则】
{indicators_text}

请你严格参考以上规则，完成以下任务:
1. 明确给出当前建议：加仓、减仓、清仓、继续持有或暂时观望，必须给出一个主结论。
2. 说明触发该建议的关键指标和对应阈值，指出哪些条件已经满足、哪些存在不确定。
3. 给出执行方案：建议一次性还是分批操作，大致价格区间，以及建议的目标仓位区间。
4. 如果结论是暂时观望，请说明下一次重点需要观察的 2-3 个指标、建议的观察频率。

回答要求使用中文，Markdown 格式，结构清晰，有小标题和条目列表。"""
    
    ai_response = call_volcengine_api(prompt)
    if ai_response.startswith("Error"):
        return jsonify({"status": "error", "error": ai_response})
    
    ts = master.portfolio.save_decision(holding['ticker'], indicators_text, ai_response)
    return jsonify({"status": "success", "result": ai_response, "timestamp": ts})

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

@app.route('/api/portfolio/groups/reorder', methods=['POST'])
def reorder_groups():
    data = request.json
    group_ids = data.get('group_ids')
    if not group_ids or not isinstance(group_ids, list):
        return jsonify({"error": "Invalid group_ids"}), 400
        
    if master.portfolio.reorder_groups(group_ids):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to reorder groups"}), 500

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
    note = data.get('note')
    name = data.get('name')
    
    if master.portfolio.add_holding(ticker, shares, cost, group_id, note, name=name):
        return jsonify({"status": "success"})
    return jsonify({"error": "Failed to add holding"}), 500

@app.route('/api/portfolio/holdings/<ticker>', methods=['PUT'])
def update_holding(ticker):
    data = request.json
    # Ticker in URL is authoritative, but we normalize it just in case
    normalized_ticker = master._normalize_ticker(ticker)
    
    shares = float(data.get('shares', 0))
    cost = float(data.get('cost', 0))
    group_id = data.get('group_id', 'default')
    note = data.get('note')
    name = data.get('name')
    
    if master.portfolio.update_holding(normalized_ticker, shares, cost, group_id, note, name=name):
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
            
            # Determine change percent (prioritize Sina)
            change_percent = pe_data.get('change_percent', 0)
            if cn_info and 'day_change_percent' in cn_info:
                change_percent = cn_info['day_change_percent']

            # Convert change_percent to decimal for consistency with dividend_yield in frontend
            # Sina returns percentage (e.g. 1.5 for 1.5%), but frontend watchlist expects decimal (0.015)
            change_percent_decimal = change_percent / 100.0

            enriched_watchlist.append({
                "ticker": raw_ticker,
                "name": name,
                "price": current_price if current_price is not None else "N/A",
                "pe": pe_data.get('trailing_pe') or '--',
                "dividend_yield": pe_data.get('dividend_yield') or 0,
                "change_percent": round(change_percent_decimal, 4)
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

@app.route('/api/reports/proxy')
def proxy_report():
    url = request.args.get('url')
    if not url:
        return "Missing URL", 400
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://data.eastmoney.com/"
    }

    try:
        req = requests.get(url, headers=headers, stream=True)
        return Response(stream_with_context(req.iter_content(chunk_size=1024)), content_type=req.headers['content-type'])
    except Exception as e:
        print(f"Proxy error: {e}")
        return "Error fetching report", 500

if __name__ == '__main__':
    # 允许局域网访问 (Host=0.0.0.0)
    app.run(debug=True, host='0.0.0.0', port=5000)
