#!/usr/bin/env python3
"""商品页面解析模块 - 使用 Playwright 浏览器抓取"""

import re
import asyncio
from urllib.parse import urlparse
from playwright.async_api import async_playwright

class StockMonitor:
    def __init__(self):
        self.browser = None
        self.playwright = None
    
    async def init_browser(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
    
    async def fetch(self, url):
        try:
            await self.init_browser()
            page = await self.browser.new_page()
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)
            html = await page.content()
            await page.close()
            return html
        except Exception as e:
            print(f"Fetch error: {e}")
            return None

    async def parse_product(self, url):
        html = await self.fetch(url)
        if not html:
            return None
        
        domain = urlparse(url).netloc
        return {
            'merchant': self.get_merchant(html, domain, url),
            'name': self.get_name(html, url),
            'price': self.get_price(html),
            'specs': self.get_specs(html),
            'in_stock': self.check_stock(html)
        }
    
    def get_merchant(self, html, domain, url):
        # 从域名提取
        name = domain.replace('my.', '').replace('www.', '').split('.')[0]
        return name.upper()

    def get_name(self, html, url):
        # 从 URL 提取
        if '/store/' in url:
            name = url.split('/')[-1].split('?')[0]
            return name.replace('-', ' ').title()[:50]
        # 从 h1 提取
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        if m:
            return m.group(1).strip()[:50]
        return "未知商品"

    def get_price(self, html):
        # WHMCS 价格格式
        patterns = [
            r'\$(\d+\.?\d*)\s*USD\s*Monthly',
            r'\$(\d+\.?\d*)\s*USD',
            r'Starting from[^$]*\$(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*USD/月',
        ]
        for p in patterns:
            m = re.search(p, html, re.I)
            if m:
                return f"${m.group(1)}/月"
        return "价格未知"

    def get_specs(self, html):
        specs = []
        # vCPU
        m = re.search(r'vCPU\s*(?:Core\s*)?(\d+)|(\d+)\s*Core', html, re.I)
        if m:
            specs.append(f"{m.group(1) or m.group(2)}C")
        # RAM
        m = re.search(r'RAM\s*(\d+)\s*GB|(\d+)\s*GB\s*RAM', html, re.I)
        if m:
            specs.append(f"{m.group(1) or m.group(2)}G")
        # Disk
        m = re.search(r'Disk\s*(\d+)\s*GB|(\d+)\s*GB\s*SSD', html, re.I)
        if m:
            specs.append(f"{m.group(1) or m.group(2)}G")
        # Traffic
        m = re.search(r'Traffic\s*([\d.]+)\s*TB|([\d.]+)\s*TB', html, re.I)
        if m:
            specs.append(f"{m.group(1) or m.group(2)}T")
        return '/'.join(specs) if specs else ""

    def check_stock(self, html):
        html_lower = html.lower()
        # 缺货关键词
        out_kw = ['0 available', 'out of stock', 'sold out', '缺货', '售罄']
        for kw in out_kw:
            if kw in html_lower:
                return False
        # 有货关键词
        in_kw = ['available', 'in stock', 'order now', '有货']
        for kw in in_kw:
            if kw in html_lower:
                return True
        return True
