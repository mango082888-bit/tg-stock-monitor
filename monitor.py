#!/usr/bin/env python3
"""商品页面解析模块"""

import re
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse

class StockMonitor:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    async def fetch(self, url):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=15) as resp:
                    return await resp.text()
        except:
            return None
    
    async def parse_product(self, url):
        html = await self.fetch(url)
        if not html:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        domain = urlparse(url).netloc
        
        return {
            'merchant': self.get_merchant(soup, domain),
            'name': self.get_name(soup),
            'price': self.get_price(soup, html),
            'specs': self.get_specs(soup, html),
            'in_stock': self.check_stock(soup, html)
        }
    
    def get_merchant(self, soup, domain):
        title = soup.find('title')
        if title:
            text = title.get_text().strip()
            for sep in [' - ', ' | ', ' – ', ' — ']:
                if sep in text:
                    return text.split(sep)[-1].strip()[:20]
        return domain.replace('www.', '').split('.')[0].upper()
    
    def get_name(self, soup):
        h1 = soup.find('h1')
        if h1:
            return h1.get_text().strip()[:50]
        title = soup.find('title')
        if title:
            text = title.get_text().strip()
            for sep in [' - ', ' | ']:
                if sep in text:
                    return text.split(sep)[0].strip()[:50]
        return "未知商品"
    
    def get_price(self, soup, html):
        patterns = [
            r'[\$¥￥]\s*(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*[/月年]',
        ]
        for p in patterns:
            m = re.search(p, html)
            if m:
                return f"${m.group(1)}"
        return "价格未知"
    
    def get_specs(self, soup, html):
        patterns = [
            r'(\d+C/\d+G/\d+G/[\d.]+T)',
            r'(\d+\s*核.*?内存)',
            r'(\d+\s*vCPU.*?RAM)',
        ]
        for p in patterns:
            m = re.search(p, html, re.I)
            if m:
                return m.group(1)
        return ""
    
    def check_stock(self, soup, html):
        html_lower = html.lower()
        out_kw = ['out of stock', 'sold out', '缺货', '售罄', '已售完', '暂无库存']
        for kw in out_kw:
            if kw in html_lower:
                return False
        in_kw = ['in stock', 'add to cart', '有货', '立即购买', '加入购物车']
        for kw in in_kw:
            if kw in html_lower:
                return True
        return True
