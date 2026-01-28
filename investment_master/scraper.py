import requests
from bs4 import BeautifulSoup
import re
import time
import os
import uuid
from playwright.sync_api import sync_playwright

class ArticleScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }

    def scrape(self, url):
        """
        Scrapes the given URL and returns a dictionary with title, content (markdown), and author.
        """
        print(f"Scraping URL: {url}")
        
        # Use Playwright for Xueqiu or if requests fails
        if 'xueqiu.com' in url:
            return self._scrape_with_playwright(url)
            
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            
            # Check for WAF or block pages
            if "aliyun_waf" in response.text or "Verification" in response.text:
                 print("Detected WAF/Block with requests, switching to Playwright...")
                 return self._scrape_with_playwright(url)

            soup = BeautifulSoup(response.text, 'html.parser')
            return self._parse_soup(soup, url)

        except Exception as e:
            print(f"Requests scraping failed: {e}, switching to Playwright...")
            return self._scrape_with_playwright(url)

    def _scrape_with_playwright(self, url):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
                )
                page = context.new_page()
                # Anti-detection script
                page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                
                print(f"Playwright navigating to {url}...")
                page.goto(url, wait_until='domcontentloaded')
                
                # Specific wait for Xueqiu
                if 'xueqiu.com' in url:
                    try:
                        page.wait_for_selector('.article__bd, .article-body', timeout=10000)
                    except:
                        print("Timeout waiting for Xueqiu article body")

                content_html = page.content()
                browser.close()
                
                soup = BeautifulSoup(content_html, 'html.parser')
                return self._parse_soup(soup, url)
                
        except Exception as e:
            print(f"Playwright scraping failed: {e}")
            return {"error": str(e)}

    def _parse_soup(self, soup, url):
        # 1. Extract Title
        title = self._extract_title(soup)
        
        # 2. Extract Content (and convert to Markdown)
        content = self._extract_content(soup, url)
        
        # 3. Extract Author (Best Effort)
        author = self._extract_author(soup)

        if not content:
            content = "Could not extract content."

        return {
            "title": title,
            "content": content,
            "author": author,
            "url": url
        }

    def _extract_title(self, soup):
        # Try h1
        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)
        # Try title tag
        if soup.title:
            return soup.title.get_text(strip=True).split('-')[0].strip()
        return "Unknown Title"

    def _extract_author(self, soup):
        # Common patterns for author
        meta_author = soup.find('meta', attrs={'name': 'author'})
        if meta_author:
            return meta_author.get('content')
            
        # Xueqiu specific
        user_name = soup.find('a', class_='user-name') or soup.find('span', class_='user-name')
        if user_name:
            return user_name.get_text(strip=True)
            
        # Generic
        for cls in ['author', 'byline', 'writer']:
            tag = soup.find(class_=re.compile(cls, re.I))
            if tag:
                return tag.get_text(strip=True)
        
        return "Unknown Author"

    def _download_image(self, img_url):
        """
        Downloads image and returns local path (relative to static).
        """
        try:
            if not img_url:
                return None
                
            # Handle protocol-less URLs
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            
            # Create directory if not exists
            save_dir = os.path.join(os.getcwd(), 'static', 'article_images')
            os.makedirs(save_dir, exist_ok=True)
            
            # Generate unique filename
            # Try to guess extension
            ext = '.jpg'
            if '.png' in img_url.lower(): ext = '.png'
            elif '.gif' in img_url.lower(): ext = '.gif'
            elif '.webp' in img_url.lower(): ext = '.webp'
            
            filename = f"{uuid.uuid4()}{ext}"
            filepath = os.path.join(save_dir, filename)
            
            # Download
            print(f"Downloading image: {img_url}")
            resp = requests.get(img_url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                return f"/static/article_images/{filename}"
            else:
                print(f"Failed to download image: {resp.status_code}")
                return img_url # Fallback to remote URL
        except Exception as e:
            print(f"Image download error: {e}")
            return img_url # Fallback

    def _extract_content(self, soup, url):
        """
        Extracts the main content and converts it to simple Markdown.
        """
        # Strategy: Find the container with the most text or specific class names
        content_div = None
        
        # 1. Site-specific selectors
        if 'xueqiu.com' in url:
            content_div = soup.find('div', class_='article__bd') or soup.find('div', class_='article-body')
        elif 'mp.weixin.qq.com' in url:
            content_div = soup.find('div', id='js_content')
        elif 'zhihu.com' in url:
            content_div = soup.find('div', class_='Post-RichText')
            
        # 2. Generic fallback: find div with most p tags
        if not content_div:
            max_p = 0
            best_div = None
            for div in soup.find_all('div'):
                # Heuristic: Div should have substantial text length
                if len(div.get_text(strip=True)) < 100:
                    continue
                    
                p_count = len(div.find_all('p', recursive=False))
                if p_count > max_p:
                    max_p = p_count
                    best_div = div
            content_div = best_div

        if not content_div:
            return ""

        # Convert to Markdown
        markdown_lines = []
        for element in content_div.descendants:
            if element.name == 'p':
                text = element.get_text(strip=True)
                if text:
                    markdown_lines.append(f"{text}\n")
            elif element.name == 'img':
                src = element.get('data-original') or element.get('src')
                if src and not src.startswith('data:'):
                    # Download image
                    local_src = self._download_image(src)
                    if local_src:
                        markdown_lines.append(f"![Image]({local_src})\n")
            elif element.name in ['h1', 'h2', 'h3', 'h4']:
                level = int(element.name[1])
                markdown_lines.append(f"{ '#' * level } {element.get_text(strip=True)}\n")
            elif element.name == 'li':
                 text = element.get_text(strip=True)
                 if text:
                     markdown_lines.append(f"- {text}\n")
        
        return "\n".join(markdown_lines)
