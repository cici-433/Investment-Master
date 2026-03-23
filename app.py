from flask import Flask, render_template, jsonify, request, Response, stream_with_context
from investment_master.core import InvestmentMaster
from investment_master.scraper import ArticleScraper
import traceback
import requests
import os
import re

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

_valuation_categories_cache = {"mtime": None, "categories": None}

def _load_valuation_markdown():
    path = os.path.join(os.path.dirname(__file__), '估值体系.md')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ""

def _extract_valuation_categories(markdown_text):
    if not markdown_text:
        return []

    lines = markdown_text.splitlines()
    pattern = re.compile(r'^(\d+)\）\s*(.+?)\s*$')
    candidates = []
    for idx, line in enumerate(lines):
        m = pattern.match(line)
        if not m:
            continue
        cid = m.group(1)
        title = m.group(2)
        candidates.append((idx, cid, title))

    matches = []
    for idx, cid, title in candidates:
        for j in range(idx + 1, min(idx + 8, len(lines))):
            nxt = lines[j].strip()
            if not nxt:
                continue
            if pattern.match(nxt):
                break
            if nxt.startswith('-') and '主估值法' in nxt:
                matches.append((idx, cid, title))
                break

    categories = []
    for i, (start_idx, cid, title) in enumerate(matches):
        end_idx = matches[i + 1][0] if i + 1 < len(matches) else len(lines)
        snippet = "\n".join(lines[start_idx:end_idx]).strip()
        if snippet:
            snippet += "\n"
        categories.append({"id": cid, "title": title, "markdown": snippet})
    return categories

def _get_valuation_categories():
    path = os.path.join(os.path.dirname(__file__), '估值体系.md')
    try:
        mtime = os.path.getmtime(path)
    except Exception:
        mtime = None
    cached = _valuation_categories_cache
    if cached["mtime"] == mtime and cached["categories"] is not None:
        return cached["categories"]

    md = _load_valuation_markdown()
    categories = _extract_valuation_categories(md)
    cached["mtime"] = mtime
    cached["categories"] = categories
    return categories

def _get_valuation_category_title_map():
    return {c.get("id"): c.get("title") for c in _get_valuation_categories() if c.get("id")}

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

@app.route('/api/valuation/categories', methods=['GET'])
def get_valuation_categories():
    cats = _get_valuation_categories()
    return jsonify({
        "status": "success",
        "categories": [{"id": c.get("id"), "title": c.get("title")} for c in cats if c.get("id")]
    })

@app.route('/api/valuation/categories/<category_id>', methods=['GET'])
def get_valuation_category_detail(category_id):
    cid = str(category_id or '').strip()
    for c in _get_valuation_categories():
        if c.get("id") == cid:
            return jsonify({
                "status": "success",
                "id": c.get("id"),
                "title": c.get("title"),
                "markdown": c.get("markdown", "")
            })
    return jsonify({"status": "error", "error": "Category not found"}), 404

@app.route('/api/analyze/verify/<ticker>')
def verify_stock_quality(ticker):
    try:
        normalized = master._normalize_ticker(ticker)
        force_refresh = request.args.get('force') == 'true'
        
        # 1. Check Local Cache
        if not force_refresh:
            cached_data = master.verification_manager.get_verification(normalized)
            if cached_data:
                return jsonify({"result": cached_data['content'], "cached": True, "timestamp": cached_data['timestamp']})
        
        # 2. Get Basic Data
        current_price = master.valuator.get_current_price(normalized)
        pe_data = master.valuator.calculate_pe(normalized) or {}
        pb_data = master.valuator.calculate_pb_roe(normalized) or {}
        
        cn_info = get_cn_stock_info(normalized)
        name = normalized
        if cn_info and cn_info.get('name'):
            name = cn_info['name']
            
        import yfinance as yf
        stock = yf.Ticker(normalized)
        try:
            info = stock.info
        except:
            info = {}
            
        sector = info.get('sector', '未知行业')
        industry = info.get('industry', '未知细分行业')
        mcap = info.get('marketCap', 0)
        
        # Format Market Cap
        if mcap > 100000000:
            mcap_str = f"{mcap / 100000000:.2f} 亿"
        else:
            mcap_str = f"{mcap / 10000:.2f} 万"

        # 3. Construct Prompt
        prompt = f"""
        请你扮演一位专业的价值投资专家，利用以下“4大工具”框架，对股票 {name} ({normalized}) 进行全方位的定性和定量验证，判断其是否值得投资。
        
        【基本数据】
        - 价格: {current_price}
        - 市值: {mcap_str}
        - 行业: {sector} - {industry}
        - PE(TTM): {pe_data.get('pe_ttm', '未知')}
        - PB: {pb_data.get('pb_current', '未知')}
        - ROE: {pb_data.get('roe_current', '未知')}%
        
        【验证框架】
        1. **用望远镜验证公司的赛道** (Good Track)
           - 行业空间与增长趋势（向上/稳定/向下）。
           - 行业属性分析：
             - 消费：品牌壁垒、规模优势、弱周期？
             - 科技：研发投入、下游应用空间？
             - 周期：宏观影响、供需关系、产能退出难度？
           - 竞争格局：市场集中度(CR4)、价格战激烈程度。
           - 产业链地位：上下游是否强势（定价权）。
           - 市场结构：大行业小龙头 vs 小行业大龙头。
           
        2. **用透视镜寻找公司的护城河** (Good Company - Moat)
           - 核心竞争力：品牌、网络效应、成本优势、转换成本、渠道优势。
           - 技术是否转化为产品/品牌力？
           - 护城河的稳固性与变迁风险。
           
        3. **用显微镜检验公司财务状况** (Financial Health)
           - 成长能力：营收/利润增长率（>20%高成长，5-10%普通）。
           - 盈利能力：毛利率、净利率、ROE趋势。
           - 经营效率：存货/应收账款/固定资产周转率（效率越高越好）。
           
        4. **用公平秤评估股票性价比** (Good Price)
           - 好公司不等于好股票（价格因素）。
           - 绝对估值(DCF)与相对估值(PE/PB)视角。
           - 结合成长性的估值判断（PEG）。

        【输出要求】
        - 请基于你已有的知识库（招股书、研报、历史数据等）进行分析。
        - 输出格式为 Markdown。
        - 每一个维度都要给出明确的“定性评价”（如：赛道优质、护城河深、财务健康、估值合理等）。
        - 最后给出一个“综合验证结论”：强烈推荐 / 谨慎推荐 / 观望 / 不推荐，并说明核心理由。
        """
        
        ai_response = call_volcengine_api(prompt)
        
        # 4. Save Result
        metadata = {
            "price": current_price,
            "pe": pe_data.get('pe_ttm'),
            "pb": pb_data.get('pb_current'),
            "roe": pb_data.get('roe_current')
        }
        master.verification_manager.save_verification(normalized, ai_response, metadata)
        
        return jsonify({"result": ai_response})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

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

@app.route('/api/journal/daily_review', methods=['POST'])
def generate_daily_review():
    data = request.json or {}
    date = data.get('date')
    benchmark_ticker = data.get('benchmark') or '000001.SS'
    holdings = master.portfolio.get_holdings()
    enriched = []
    total_prev = 0.0
    total_curr = 0.0
    for h in holdings:
        raw_ticker = h.get('ticker')
        if not raw_ticker:
            continue
        ticker = master._normalize_ticker(raw_ticker)
        if ticker == 'CASH':
            continue
        shares = float(h.get('shares') or 0)
        name = h.get('name') or raw_ticker
        cn_info = get_cn_stock_info(ticker)
        current_price = None
        pre_close = None
        day_change_percent = 0.0
        if cn_info:
            current_price = cn_info.get('current_price')
            pre_close = cn_info.get('pre_close')
            v = cn_info.get('day_change_percent')
            if v is not None:
                day_change_percent = float(v)
        if current_price in (None, 0):
            try:
                cp = master.valuator.get_current_price(ticker)
            except Exception:
                cp = None
            if cp is not None:
                current_price = cp
        if pre_close is None and current_price is not None and day_change_percent:
            pre_close = current_price / (1 + day_change_percent / 100)
        if current_price is not None and pre_close is not None and shares > 0:
            prev_value = pre_close * shares
            curr_value = current_price * shares
            contribution = curr_value - prev_value
            total_prev += prev_value
            total_curr += curr_value
        else:
            prev_value = 0.0
            curr_value = 0.0
            contribution = 0.0
        note = h.get('note') or ''
        short_note = note.replace('\n', ' ')
        if len(short_note) > 80:
            short_note = short_note[:80] + '...'
        enriched.append({
            "name": name,
            "ticker": raw_ticker,
            "shares": shares,
            "current_price": current_price,
            "pre_close": pre_close,
            "day_change_percent": day_change_percent,
            "prev_value": prev_value,
            "curr_value": curr_value,
            "contribution": contribution,
            "group_id": h.get("group_id", "default"),
            "note": short_note
        })
    if total_prev > 0:
        portfolio_return = (total_curr - total_prev) / total_prev * 100
    else:
        portfolio_return = 0.0
    benchmark_info = get_cn_stock_info(benchmark_ticker)
    benchmark_name = benchmark_ticker
    benchmark_change = None
    if benchmark_info:
        if benchmark_info.get('name'):
            benchmark_name = benchmark_info.get('name')
        v = benchmark_info.get('day_change_percent')
        if v is not None:
            benchmark_change = float(v)
    enriched_sorted = sorted(enriched, key=lambda x: abs(x.get('contribution', 0)), reverse=True)
    top_lines = []
    for i, item in enumerate(enriched_sorted):
        if i >= 6:
            break
        line = f"- {item['name']} ({item['ticker']}): 涨跌 {item['day_change_percent']:.2f}%, 市值约 {item['curr_value']:.0f} 元, 当日盈亏约 {item['contribution']:.0f} 元, 备注: {item['note']}"
        top_lines.append(line)
    holdings_lines = []
    for item in enriched:
        if item['curr_value'] == 0 and item['prev_value'] == 0:
            continue
        line = f"- {item['name']} ({item['ticker']}): 涨跌 {item['day_change_percent']:.2f}%, 市值约 {item['curr_value']:.0f} 元, 当日盈亏约 {item['contribution']:.0f} 元, 备注: {item['note']}"
        holdings_lines.append(line)
    date_str = date or ''
    
    # Calculate relative performance safely
    relative_perf = "未知"
    if benchmark_change is not None:
        diff = portfolio_return - benchmark_change
        relative_perf = f"{diff:.2f}%"

    # Calculate top gainer and loser
    active_holdings = [h for h in enriched if h['curr_value'] > 0]
    sorted_by_change = sorted(active_holdings, key=lambda x: x.get('day_change_percent', 0), reverse=True)
    top_gainer = sorted_by_change[0] if sorted_by_change else None
    top_loser = sorted_by_change[-1] if sorted_by_change else None
    
    gainer_info = f"{top_gainer['name']} (涨幅 {top_gainer['day_change_percent']:.2f}%)" if top_gainer else "无"
    loser_info = f"{top_loser['name']} (跌幅 {top_loser['day_change_percent']:.2f}%)" if top_loser else "无"

    prompt = f"""
你是一位成熟的个人投资者（类似“ETF拯救世界”或“孟岩”的风格），同时借鉴了“女娲补仓”的犀利点评风格。
你的风格核心是：**理性、平和、不预测市场、但对板块强弱有明确的策略判断**。

请根据以下数据，写一篇今天的复盘日志。

【数据概览】
- 日期: {date_str if date_str else "今天"}
- 我的收益: {portfolio_return:.2f}% (跑赢大盘 {relative_perf})
- 基准({benchmark_name}): {benchmark_change if benchmark_change is not None else "未知"}%
- 领涨持仓: {gainer_info}
- 领跌持仓: {loser_info}
- 核心持仓:
{"" .join([chr(10) + l for l in top_lines]) if top_lines else "暂无有效数据"}

【写作要求】
1. **标题**: 自拟一个有点“佛系”但有观点的标题（例如：“大涨之后，聊聊风险”、“又是无聊震荡的一天”）。
2. **第一部分：账户与大盘**
   - 直接对比收益，用一句话点评今天的表现（满意/一般/侥幸）。
   - 分析原因：是因为重仓了哪个板块？还是运气好？
3. **第二部分：市场碎碎念 (重点)**
   - **不要**写成新闻通稿！不要堆砌宏观数据！
   - 要写成“博主与读者的对话”：
     - "今天市场很有意思..."
     - "很多人问我..."
     - "其实..."
   - 点评1-2个热门板块（如科技、白酒、新能源），但要用**估值**和**情绪**的视角，而不是技术分析。
   - 语气要像老朋友聊天，多用短句。
   - 核心观点：涨了不狂，跌了不慌，盈亏同源。
4. **第三部分：板块强弱与策略 (仿“女娲补仓”风格)**
   - **重点分析**今日涨跌幅最剧烈的两个方向：
   - **领涨方向 ({gainer_info})**：
     - 为什么涨？是反转还是反弹？
     - 策略建议：是该“适度止盈”、“减仓换基”还是“继续持有”？给出明确的理由（如“仓位重建议减点”、“还在低位拿住不动”）。
   - **领跌方向 ({loser_info})**：
     - 为什么跌？是错杀还是基本面恶化？
     - 策略建议：是“机会是跌出来的”可以补仓，还是“趋势坏了”要止损？
     - 语气要犀利一点，直接给干货。
5. **第四部分：操作与策略 (整体)**
   - 结合今天的行情，给出接下来的应对心态。
   - 强调：**“不预测，只应对”**。
   - 总结今天的操作思考（如果有）。
6. **结尾**: 一句“鸡汤”或“定心丸”，加上标准免责声明。

【语气示例】
- “市场永远是对的，错的只有我们自己。”
- “今天这个走势，估计不少人又坐不住了。”
- “慢慢变富，才是最快的捷径。”
- “关于XX板块，我的建议很明确：人多的地方不要去。”

请按上述风格输出 Markdown 格式。
"""
    ai_response = call_volcengine_api(prompt)
    if isinstance(ai_response, str) and ai_response.startswith("Error"):
        return jsonify({"status": "error", "error": ai_response}), 500
    return jsonify({
        "status": "success",
        "content": ai_response,
        "portfolio_return": portfolio_return,
        "benchmark": {
            "ticker": benchmark_ticker,
            "name": benchmark_name,
            "day_change_percent": benchmark_change
        },
        "timestamp": __import__('time').time()
    })

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
    title_map = _get_valuation_category_title_map()
    
    for h in holdings:
        raw_ticker = h['ticker']
        ticker = master._normalize_ticker(raw_ticker)
        
        try:
            if ticker == 'CASH':
                current_price = 1.0
                name = '现金 (CNY)'
                market_value = h['shares']
                cost_basis = h['cost']
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
                    "note": h.get("note", ""),
                    "strategy": h.get("strategy", ""),
                    "valuation_category_id": h.get("valuation_category_id") or h.get("valuation_category") or "",
                    "valuation_category_title": title_map.get(str(h.get("valuation_category_id") or h.get("valuation_category") or "")) or "",
                    "sector": "Cash",
                    "industry": "Cash",
                    "sector_cn": "现金",
                    "industry_cn": "现金"
                })
                continue

            # 1. Try to get basic info (Price, Name) from CN API first (faster/more reliable for A-shares)
            cn_info = get_cn_stock_info(ticker)
            
            name = h.get('name') # Prefer saved name
            current_price = None
            pre_close = None
            day_change_percent = 0.0
            
            if cn_info:
                if not name:
                    name = cn_info.get('name')
                current_price = cn_info.get('current_price')
                pre_close = cn_info.get('pre_close')
                day_change_percent = cn_info.get('day_change_percent', 0.0)
            
            # --- Sector/Industry Enrichment (Disabled) ---
            # sector = h.get('sector')
            # industry = h.get('industry')
            
            # If missing, fetch and save (only for valid tickers)
            # Use the fetched name for better guessing if yfinance fails
            # if ticker != 'CASH' and (not sector or not industry or sector == 'Unknown'):
            #     try:
            #         # Only fetch if we haven't tried recently (optional optimization, skip for now)
            #         print(f"Fetching sector info for {ticker} ({name})...")
            #         info = master.valuator.get_sector_info(ticker, name)
            #         if info:
            #             sector = info.get('sector')
            #             industry = info.get('industry')
            #             # Save to DB so we don't fetch again
            #             master.portfolio.update_holding_metadata(raw_ticker, {
            #                 "sector": sector,
            #                 "industry": industry
            #             })
            #     except Exception as e:
            #         print(f"Error enriching sector for {ticker}: {e}")

            # Translate
            sector_cn = "" # SECTOR_MAP.get(sector, sector) if sector else "未知板块"
            industry_cn = "" # INDUSTRY_MAP.get(industry, industry) if industry else "未知行业"
            
            # 2. Fallback to Valuator (yfinance) if price missing
            if current_price is None:
                current_price = master.valuator.get_current_price(ticker)
            
            # If still None, use cost as fallback to avoid crashes (or 0)
            if current_price is None:
                current_price = h.get('cost', 0)
                
            shares = h['shares']
            cost_basis = h['cost']
            
            market_value = shares * current_price
            gain = market_value - (shares * cost_basis)
            if shares > 0 and cost_basis > 0:
                gain_percent = (gain / (shares * cost_basis)) * 100
            else:
                gain_percent = 0
            
            # Calculate Day Gain
            day_gain = 0.0
            if pre_close:
                day_gain = (current_price - pre_close) * shares
            
            enriched_holdings.append({
                "ticker": raw_ticker,
                "name": name,
                "shares": shares,
                "cost": cost_basis,
                "current_price": current_price,
                "market_value": round(market_value, 2),
                "gain": round(gain, 2),
                "gain_percent": round(gain_percent, 2),
                "day_change_percent": round(day_change_percent, 2),
                "day_gain": round(day_gain, 2),
                "group_id": h.get("group_id", "default"),
                "note": h.get("note", ""),
                "strategy": h.get("strategy", ""),
                "valuation_category_id": h.get("valuation_category_id") or h.get("valuation_category") or "",
                "valuation_category_title": title_map.get(str(h.get("valuation_category_id") or h.get("valuation_category") or "")) or "",
                "sector": "", # sector,
                "industry": "", # industry,
                "sector_cn": "", # sector_cn,
                "industry_cn": "" # industry_cn
            })
            
        except Exception as e:
            print(f"Error processing holding {raw_ticker}: {e}")
            traceback.print_exc()
            # Fallback to safe raw data with defaults to prevent frontend crash
            h_safe = h.copy()
            h_safe.setdefault('market_value', 0)
            h_safe.setdefault('gain', 0)
            h_safe.setdefault('day_gain', 0)
            h_safe.setdefault('current_price', 0)
            h_safe.setdefault('gain_percent', 0)
            h_safe.setdefault('day_change_percent', 0)
            h_safe.setdefault('name', raw_ticker)
            h_safe.setdefault('group_id', 'default')
            enriched_holdings.append(h_safe)
            
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
    market_cap_str = "未知"
    pe_data = None
    pb_data = None
    
    # 1. Try to get basic info (Price, Name) from CN API first (faster/more reliable for A-shares)
    cn_info = get_cn_stock_info(normalized)
    if cn_info:
        if not name:
            name = cn_info.get('name')
        if cn_info.get('current_price'):
            current_price = cn_info.get('current_price')
    
    try:
        # 2. If price still missing, try Valuator
        if current_price is None:
            current_price = master.valuator.get_current_price(normalized)
            
        pe_data = master.valuator.calculate_pe(normalized)
        import yfinance as yf
        stock = yf.Ticker(normalized)
        try:
            info = stock.info
        except:
            info = {}
            
        # Extract Market Cap
        mcap = info.get('marketCap')
        if mcap:
            if mcap > 100000000:
                market_cap_str = f"{mcap / 100000000:.2f} 亿"
            else:
                market_cap_str = f"{mcap / 10000:.2f} 万"
                
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
- 总市值: {market_cap_str}
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

@app.route('/api/portfolio/decision/system', methods=['POST'])
def holding_system_decision():
    data = request.json or {}
    ticker = data.get('ticker')
    action = data.get('action', 'buy')
    if not ticker:
        return jsonify({"status": "error", "error": "Ticker is required"}), 400
    if action not in ('buy', 'sell'):
        return jsonify({"status": "error", "error": "Invalid action"}), 400
    
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
    market_cap_str = "未知"
    pe_data = None
    pb_data = None
    
    cn_info = get_cn_stock_info(normalized)
    if cn_info:
        if not name:
            name = cn_info.get('name')
        if cn_info.get('current_price'):
            current_price = cn_info.get('current_price')
    
    try:
        if current_price is None:
            current_price = master.valuator.get_current_price(normalized)
            
        pe_data = master.valuator.calculate_pe(normalized)
        import yfinance as yf
        stock = yf.Ticker(normalized)
        try:
            info = stock.info
        except:
            info = {}
            
        mcap = info.get('marketCap')
        if mcap:
            if mcap > 100000000:
                market_cap_str = f"{mcap / 100000000:.2f} 亿"
            else:
                market_cap_str = f"{mcap / 10000:.2f} 万"
                
        pb_data = master.valuator.calculate_pb_roe(normalized, info=info)
    except Exception as e:
        print(f"Error in system decision valuation for {normalized}: {e}")
    
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
    
    valuation_summary = "暂无完整估值数据，可更多依赖投资体系规则与观察指标。"
    if valuation_lines:
        valuation_summary = "\n".join(f"- {line}" for line in valuation_lines)
    
    checklist = master.system_manager.get_checklist(type=action) or {}
    items = checklist.get("items") if isinstance(checklist, dict) else []
    mode = checklist.get("mode") if isinstance(checklist, dict) else "all"
    source = checklist.get("source") if isinstance(checklist, dict) else "checklist"
    if mode not in ("all", "any"):
        mode = "all"
    
    rule_lines = []
    for it in items or []:
        if isinstance(it, dict):
            text = (it.get("text") or "").strip()
            required = it.get("required", True) is True
        else:
            text = str(it).strip()
            required = True
        if not text:
            continue
        prefix = "必选" if required else "可选"
        rule_lines.append(f"- 【{prefix}】{text}")
    rules_text = "（暂无规则）" if not rule_lines else "\n".join(rule_lines)
    
    mode_text = "全部确认" if mode == "all" else "满足任一"
    source_text = "我的投资体系" if source == "my_system" else "默认检查单"
    action_text = "买入" if action == "buy" else "卖出"
    
    strategy_text = holding.get("strategy") or ""
    note_text = holding.get("note") or ""
    
    prompt = f"""你是一个严格执行“投资体系”的投资助手，请先判断当前是否适合{action_text}这只股票，必须给出一个明确结论（适合 / 不适合 / 条件不足），并且说明依据。

【标的基本信息】
- 名称: {name or '未知'}
- 代码: {normalized}
- 当前价格: {current_price if current_price is not None else '未知'} 元
- 总市值: {market_cap_str}
- 持仓成本: {cost} 元
- 持仓数量: {shares} 股
{gain_text}

【估值与财务摘要】
{valuation_summary}

【我的投资体系决策规则（本次动作：{action_text}）】
- 来源: {source_text}
- 通过标准: {mode_text}
{rules_text}

【该标的的操作策略（如有）】
{strategy_text if strategy_text.strip() else "（无）"}

【该标的的观察指标/备注（如有）】
{note_text if note_text.strip() else "（无）"}

请完成：
1) 给出结论：现在是否适合{action_text}（三选一：适合/不适合/条件不足）。
2) 对照上面的规则逐条判断：哪些条款已满足、哪些未满足、哪些需要补充数据才能判断。
3) 给出可执行方案：如果适合，建议分批还是一次性、仓位/价格区间怎么控制；如果不适合，说明下一步需要观察的关键触发条件。
4) 用中文、Markdown 输出，结构清晰，避免空泛口号。"""
    
    ai_response = call_volcengine_api(prompt)
    if isinstance(ai_response, str) and ai_response.startswith("Error"):
        return jsonify({"status": "error", "error": ai_response})
    
    return jsonify({"status": "success", "result": ai_response, "timestamp": __import__('time').time()})

@app.route('/api/strategies', methods=['GET'])
def list_strategies():
    base_dir = os.path.join(os.path.dirname(__file__), 'strategies')
    if not os.path.isdir(base_dir):
        return jsonify([])
    
    items = []
    for name in os.listdir(base_dir):
        if not name.lower().endswith('.md'):
            continue
        if name.startswith('.'):
            continue
        file_path = os.path.join(base_dir, name)
        if not os.path.isfile(file_path):
            continue
        slug = os.path.splitext(name)[0]
        title = slug
        title_set = False
        excerpt = ''
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
            for line in lines[:80]:
                s = (line or '').strip()
                if not s:
                    continue
                if s.startswith('#'):
                    if not title_set:
                        t = s.lstrip('#').strip()
                        if t:
                            title = t
                            title_set = True
                    continue
                if not excerpt:
                    excerpt = s
            updated_at = int(os.path.getmtime(file_path))
        except Exception:
            updated_at = None
        items.append({
            "slug": slug,
            "file": name,
            "title": title,
            "excerpt": excerpt,
            "updated_at": updated_at
        })
    
    items.sort(key=lambda x: (x.get("title") or x.get("slug") or "").lower())
    return jsonify(items)

@app.route('/api/strategies/<slug>', methods=['GET'])
def get_strategy(slug):
    if not slug or not re.fullmatch(r'[A-Za-z0-9_-]+', slug):
        return jsonify({"error": "Invalid slug"}), 400
    base_dir = os.path.join(os.path.dirname(__file__), 'strategies')
    file_path = os.path.join(base_dir, slug + '.md')
    if not os.path.isfile(file_path):
        return jsonify({"error": "Not found"}), 404
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        updated_at = int(os.path.getmtime(file_path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    title = slug
    for line in content.splitlines()[:40]:
        s = (line or '').strip()
        if s.startswith('#'):
            t = s.lstrip('#').strip()
            if t:
                title = t
            break
    return jsonify({"slug": slug, "title": title, "content": content, "updated_at": updated_at})

@app.route('/api/strategies/ai', methods=['POST'])
def ai_strategy_summary():
    data = request.json or {}
    slug = data.get('slug')
    if not slug or not re.fullmatch(r'[A-Za-z0-9_-]+', slug):
        return jsonify({"status": "error", "error": "Invalid slug"}), 400
    base_dir = os.path.join(os.path.dirname(__file__), 'strategies')
    file_path = os.path.join(base_dir, slug + '.md')
    if not os.path.isfile(file_path):
        return jsonify({"status": "error", "error": "Not found"}), 404
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    title = slug
    for line in content.splitlines()[:40]:
        s = (line or '').strip()
        if s.startswith('#'):
            t = s.lstrip('#').strip()
            if t:
                title = t
            break
    prompt = f"""请阅读下面这一份投资策略文档，并提炼成可以直接执行的要点清单。

《{title}》原文：
{content}

请输出：
1）核心结论（一句话）
2）适用场景与不适用边界（列表）
3）执行步骤（最多 5 步），每一步给出所需数据与判断阈值
4）常见坑与规避（列表）
5）小模板：用于记录一次执行的要点（含字段名）

要求使用中文、Markdown，小标题清晰、条目简洁。"""
    ai = call_volcengine_api(prompt)
    if isinstance(ai, str) and ai.startswith("Error"):
        return jsonify({"status": "error", "error": ai})
    return jsonify({"status": "success", "result": ai})

def _guigui_strategy_dir():
    return os.path.join(os.path.dirname(__file__), '龟龟投资策略_v0.15')

def _read_text_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def _first_md_title(content, fallback):
    for line in (content or '').splitlines()[:60]:
        s = (line or '').strip()
        if s.startswith('#'):
            t = s.lstrip('#').strip()
            if t:
                return t
    return fallback

@app.route('/api/guigui_strategy/docs', methods=['GET'])
def list_guigui_docs():
    base_dir = _guigui_strategy_dir()
    if not os.path.isdir(base_dir):
        return jsonify([])

    items = []
    for name in os.listdir(base_dir):
        if not name.lower().endswith('.md'):
            continue
        if name.startswith('.'):
            continue
        file_path = os.path.join(base_dir, name)
        if not os.path.isfile(file_path):
            continue
        slug = os.path.splitext(name)[0]
        title = slug
        updated_at = None
        try:
            content = _read_text_file(file_path)
            title = _first_md_title(content, slug)
            updated_at = int(os.path.getmtime(file_path))
        except Exception:
            pass
        items.append({
            "slug": slug,
            "file": name,
            "title": title,
            "updated_at": updated_at
        })

    items.sort(key=lambda x: (x.get("file") or "").lower())
    return jsonify(items)

@app.route('/api/guigui_strategy/docs/<path:slug>', methods=['GET'])
def get_guigui_doc(slug):
    slug = (slug or '').strip()
    if not slug or os.path.basename(slug) != slug or '..' in slug:
        return jsonify({"error": "Invalid slug"}), 400

    base_dir = _guigui_strategy_dir()
    file_path = os.path.join(base_dir, slug + '.md')
    if not os.path.isfile(file_path):
        return jsonify({"error": "Not found"}), 404

    try:
        content = _read_text_file(file_path)
        updated_at = int(os.path.getmtime(file_path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    title = _first_md_title(content, slug)
    return jsonify({"slug": slug, "title": title, "content": content, "updated_at": updated_at})

@app.route('/api/guigui_strategy/ai', methods=['POST'])
def ai_guigui_strategy():
    data = request.json or {}
    step = (data.get('step') or '').strip().lower()
    stock = (data.get('stock') or '').strip()
    channel = (data.get('channel') or '').strip()
    target_year = (data.get('target_year') or '').strip()
    data_pack_market = (data.get('data_pack_market') or '').strip()
    data_pack_report = (data.get('data_pack_report') or '').strip()
    pdf_name = (data.get('pdf_name') or '').strip()

    step_map = {
        "coordinator": "coordinator",
        "phase0": "coordinator",
        "phase1": "phase1_数据采集",
        "phase2": "phase2_PDF解析",
        "phase3": "phase3_分析与报告",
    }
    if step not in step_map:
        return jsonify({"status": "error", "error": "Invalid step"}), 400

    base_dir = _guigui_strategy_dir()
    file_path = os.path.join(base_dir, step_map[step] + '.md')
    if not os.path.isfile(file_path):
        return jsonify({"status": "error", "error": "Doc not found"}), 404

    doc = _read_text_file(file_path)
    if len(doc) > 12000:
        doc = doc[:12000] + "\n\n...(内容过长已截断)"

    ctx = f"""用户输入：
- 标的：{stock or "（未填）"}
- 持股渠道：{channel or "（未填）"}
- 年报PDF：{pdf_name or "（未上传）"}
- 目标财年：{target_year or "（未填）"}"""

    if step in ("phase3",):
        if not data_pack_market:
            return jsonify({"status": "error", "error": "data_pack_market is required"}), 400
        packs = f"""data_pack_market.md：
{data_pack_market[:18000]}

data_pack_report.md（可选）：
{data_pack_report[:18000]}"""
        prompt = f"""你将协助我执行《龟龟投资策略 v0.15》的 Phase 3（分析与报告）。

策略指令（节选）：
{doc}

{ctx}

输入数据包（仅允许使用这些数据，不允许使用外部数据源、不允许猜测缺失项）：
{packs}

请输出一个可直接保存为 Markdown 的分析报告（简化版但要可执行），必须包含：
1）因子1A 五分钟快筛：按策略表格输出，并给出是否否决
2）若未否决：因子2 粗算的关键计算（展示公式+代入），给出否决门判断
3）若未否决：因子3/4 在数据不足时明确列出“缺什么数据才能算”，并给出下一步数据采集/年报提取清单
4）结论：三选一（通过/否决/数据不足），并给出下一步行动
要求中文、Markdown，小标题清晰，所有引用写明来源字段名（如 data_pack_market / data_pack_report）。"""
    else:
        prompt = f"""你将协助我把《龟龟投资策略 v0.15》的文档，转成“网页操作界面可用”的执行清单与填写模板。

策略文档：
{doc}

{ctx}

请输出 Markdown，必须包含：
1）本步骤的输入字段（字段名、示例、是否必填）
2）本步骤的操作按钮（按钮文案、点击后做什么、输出到哪里）
3）本步骤的输出物（文件名/内容结构/关键字段）
4）常见错误与界面提示文案（用户容易填错的点）
请保持内容简洁、可直接映射成界面组件。"""

    ai = call_volcengine_api(prompt, use_search=False)
    if isinstance(ai, str) and ai.startswith("Error"):
        return jsonify({"status": "error", "error": ai})
    return jsonify({"status": "success", "result": ai})

import yfinance as yf
import pandas as pd

def _normalize_symbol(ticker):
    t = master._normalize_ticker(ticker)
    base = t.split('.')[0]
    return t, base

def _df_to_year_rows(df, fields, unit_note):
    rows = []
    years = []
    try:
        if isinstance(df, pd.DataFrame):
            cols = list(df.columns)
            for c in cols[:5]:
                y = str(c.year) if hasattr(c, 'year') else str(c)
                years.append(y)
            years = years[::-1]
            for y in years:
                row = [y]
                for f in fields:
                    val = None
                    try:
                        c = df.columns[df.columns.astype(str) == y][0]
                        v = df.loc[f, c]
                        if pd.isna(v):
                            val = '⚠️缺失'
                        else:
                            val = f"{float(v):,.2f}"
                    except:
                        val = '⚠️缺失'
                    row.append(val)
                rows.append(row)
    except:
        pass
    return years, rows

def _series_to_table(s, max_rows=50):
    out = []
    try:
        if hasattr(s, 'items'):
            items = list(s.items())
            items = items[-max_rows:]
            for dt, val in items[::-1]:
                out.append((str(dt.date()) if hasattr(dt, 'date') else str(dt), f"{float(val):,.4f}"))
    except:
        pass
    return out

def _weekly_history_summary(hist):
    info = {"start": "", "end": "", "count": 0, "min": None, "min_date": "", "max": None, "max_date": "", "years": {}}
    try:
        if isinstance(hist, pd.DataFrame) and len(hist) > 0:
            info["start"] = str(hist.index[0].date())
            info["end"] = str(hist.index[-1].date())
            info["count"] = len(hist)
            closes = hist['Close']
            idx_min = closes.idxmin()
            idx_max = closes.idxmax()
            info["min"] = float(closes.min())
            info["min_date"] = str(idx_min.date())
            info["max"] = float(closes.max())
            info["max_date"] = str(idx_max.date())
            by_year = {}
            for ts, row in hist.iterrows():
                y = ts.year
                c = float(row['Close'])
                by_year.setdefault(y, {"low": c, "high": c, "last": c})
                by_year[y]["low"] = min(by_year[y]["low"], c)
                by_year[y]["high"] = max(by_year[y]["high"], c)
                by_year[y]["last"] = c
            info["years"] = by_year
    except:
        pass
    return info

def _build_data_pack_market(ticker, channel, target_year):
    t, symbol = _normalize_symbol(ticker)
    stock = yf.Ticker(t)
    info = {}
    try:
        info = stock.info
    except:
        info = {}
    name_info = get_cn_stock_info(t) or {}
    name = name_info.get("name") or info.get("shortName") or t
    sector = info.get("sector") or "Unknown"
    industry = info.get("industry") or "Unknown"
    unit_note = "所有金额单位为报表币种的百万元"
    fin = None
    bs = None
    cf = None
    try:
        fin = stock.financials
    except:
        pass
    try:
        bs = stock.balance_sheet
    except:
        pass
    try:
        cf = stock.cashflow
    except:
        pass
    inc_fields = ["Total Revenue","Cost Of Revenue","Gross Profit","Research Development","Selling General Administrative","Operating Income","Other Income Expense","Income Before Tax","Income Tax Expense","Net Income","Net Income Applicable To Common Shares","Minority Interest","Depreciation"]
    bs_fields = ["Cash And Cash Equivalents","Short Term Investments","Net Receivables","Inventory","Other Current Assets","Total Current Assets","Long Term Investments","Property Plant Equipment","Goodwill","Intangible Assets","Total Assets","Short Long Term Debt","Long Term Debt","Accounts Payable","Deferred Revenue","Total Current Liabilities","Total Liab","Total Stockholder Equity","Minority Interest"]
    cf_fields = ["Total Cash From Operating Activities","Capital Expenditures","Total Cashflows From Investing Activities","Total Cash From Financing Activities","Dividends Paid","Repurchase Of Stock","Depreciation","Change In Receivables","Change In Payables","Change In Inventory"]
    inc_years, inc_rows = _df_to_year_rows(fin, inc_fields, unit_note) if fin is not None else ([],[])
    bs_years, bs_rows = _df_to_year_rows(bs, bs_fields, unit_note) if bs is not None else ([],[])
    cf_years, cf_rows = _df_to_year_rows(cf, cf_fields, unit_note) if cf is not None else ([],[])
    div_table = _series_to_table(stock.dividends if hasattr(stock, 'dividends') else [], 80)
    hist = stock.history(period='10y', interval='1wk')
    hist_info = _weekly_history_summary(hist)
    price = info.get('currentPrice') or info.get('previousClose') or ""
    mcap = info.get('marketCap') or ""
    dy = info.get('dividendYield') or info.get('trailingAnnualDividendYield') or ""
    lines = []
    lines.append(f"# 数据包：{name}（{t}）")
    lines.append("")
    lines.append("## 1. 基础信息")
    lines.append(f"- 代码：{t}")
    lines.append(f"- 名称：{name}")
    lines.append(f"- 板块/行业：{sector} / {industry}")
    lines.append(f"- 持股渠道：{channel or '（未指定）'}")
    lines.append(f"- 分红率TTM：{dy if dy else '未知'}")
    lines.append("")
    lines.append("## 2. 市场数据")
    lines.append(f"- 当前股价：{price}")
    lines.append(f"- 总市值：{mcap}")
    lines.append("")
    lines.append("## 3. 五年损益表（单位：百万元）")
    if inc_rows:
        header = "| 年份 | " + " | ".join([f for f in inc_fields]) + " |"
        sep = "|:----|" + "|".join([":----:" for _ in inc_fields]) + "|"
        lines.append(header)
        lines.append(sep)
        for r in inc_rows:
            lines.append("| " + " | ".join(r) + " |")
    else:
        lines.append("⚠️ 获取失败")
    lines.append("")
    lines.append("## 4. 五年资产负债表（单位：百万元）")
    if bs_rows:
        header = "| 年份 | " + " | ".join([f for f in bs_fields]) + " |"
        sep = "|:----|" + "|".join([":----:" for _ in bs_fields]) + "|"
        lines.append(header)
        lines.append(sep)
        for r in bs_rows:
            lines.append("| " + " | ".join(r) + " |")
    else:
        lines.append("⚠️ 获取失败")
    lines.append("")
    lines.append("## 5. 五年现金流量表（单位：百万元）")
    if cf_rows:
        header = "| 年份 | " + " | ".join([f for f in cf_fields]) + " |"
        sep = "|:----|" + "|".join([":----:" for _ in cf_fields]) + "|"
        lines.append(header)
        lines.append(sep)
        for r in cf_rows:
            lines.append("| " + " | ".join(r) + " |")
    else:
        lines.append("⚠️ 获取失败")
    lines.append("")
    lines.append("## 6. 股息历史")
    if div_table:
        lines.append("| 除净日 | 每股股息 |")
        lines.append("|:-----|------:|")
        for d, v in div_table:
            lines.append(f"| {d} | {v} |")
    else:
        lines.append("（无记录或获取失败）")
    lines.append("")
    lines.append("## 7. 管理层与治理（占位）")
    lines.append("⚠️ 待补充：控股股东、审计师、违规记录等")
    lines.append("")
    lines.append("## 8. 行业与竞争（占位）")
    lines.append("⚠️ 待补充：竞争对手、监管动态、周期位置")
    lines.append("")
    lines.append("## 9. 子公司数据（占位）")
    lines.append("⚠️ 若为控股公司，待补充子公司列表及数据")
    lines.append("")
    lines.append("## 10. MD&A 摘要（占位）")
    lines.append("⚠️ 待补充：管理层讨论与分析摘要")
    lines.append("")
    lines.append("## 11. 10年历史价格摘要")
    lines.append(f"- 数据覆盖区间：{hist_info['start']} — {hist_info['end']}")
    lines.append(f"- 数据点数量：{hist_info['count']}")
    lines.append(f"- 10年最低价：{hist_info['min']}（{hist_info['min_date']}）")
    lines.append(f"- 10年最高价：{hist_info['max']}（{hist_info['max_date']}）")
    lines.append("")
    lines.append("年度摘要：")
    lines.append("| 年份 | 年度最低 | 年度最高 | 年末收盘 |")
    lines.append("|:----|------:|------:|------:|")
    for y in sorted(hist_info["years"].keys()):
        d = hist_info["years"][y]
        lines.append(f"| {y} | {d['low']:.4f} | {d['high']:.4f} | {d['last']:.4f} |")
    lines.append("")
    lines.append("## 12. 数据来源汇总")
    lines.append("| # | 数据项 | 来源 | URL/工具 | 获取日期 |")
    lines.append("|---|:-------|:-----|:---------|:--------:|")
    lines.append("| 1 | 市场与财务数据 | yfinance | Ticker.info/financials/balance_sheet/cashflow | N/A |")
    lines.append("")
    lines.append(f"（说明）{unit_note}")
    return "\n".join(lines), symbol

@app.route('/api/guigui_strategy/phase1/run', methods=['POST'])
def run_guigui_phase1():
    data = request.json or {}
    stock = (data.get('stock') or '').strip()
    channel = (data.get('channel') or '').strip()
    target_year = (data.get('target_year') or '').strip()
    if not stock:
        return jsonify({"status": "error", "error": "缺少标的"}), 400
    try:
        content, symbol = _build_data_pack_market(stock, channel, target_year)
        out_dir = os.path.join(os.path.dirname(__file__), 'workspace', symbol)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, 'data_pack_market.md')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"status": "success", "result": content, "file_path": out_path})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
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
    valuation_category_id = data.get('valuation_category_id') or data.get('valuation_category')
    
    if master.portfolio.add_holding(ticker, shares, cost, group_id, note, name=name, valuation_category_id=valuation_category_id):
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
    strategy = data.get('strategy')
    valuation_category_id = data.get('valuation_category_id') or data.get('valuation_category')
    
    if master.portfolio.update_holding(normalized_ticker, shares, cost, group_id, note, name=name, strategy=strategy, valuation_category_id=valuation_category_id):
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
