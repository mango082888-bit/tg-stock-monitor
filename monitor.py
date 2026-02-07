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
        
        # 检测是否是分类页面（多个商品）
        if self.is_category_page(html):
            return await self.parse_category(html, url, domain)
        
        return {
            'merchant': self.get_merchant(html, domain, url),
            'name': self.get_name(html, url),
            'price': self.get_price(html),
            'specs': self.get_specs(html),
            'in_stock': self.check_stock(html)
        }
    
    def is_category_page(self, html):
        # 多个商品卡片 = 分类页
        cards = re.findall(r'class="[^"]*package[^"]*"', html, re.I)
        return len(cards) > 1
    
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

    async def parse_category(self, html, url, domain):
        """解析分类页面，返回多个商品"""
        products = []
        merchant = self.get_merchant(html, domain, url)
        
        # 匹配 WHMCS 商品卡片
        pattern = r'<div[^>]*class="[^"]*package[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>'
        cards = re.findall(pattern, html, re.S | re.I)
        
        for card in cards:
            name = self.extract_card_name(card)
            price = self.extract_card_price(card)
            specs = self.extract_card_specs(card)
            in_stock = self.extract_card_stock(card)
            
            if name:
                products.append({
                    'merchant': merchant,
                    'name': name,
                    'price': price,
                    'specs': specs,
                    'in_stock': in_stock
                })
        
        return products if products else None

    def extract_card_name(self, card):
        m = re.search(r'<h[23][^>]*>([^<]+)</h[23]>', card, re.I)
        return m.group(1).strip()[:50] if m else None

    def extract_card_price(self, card):
        m = re.search(r'\$(\d+\.?\d*)', card)
        return f"${m.group(1)}/月" if m else "价格未知"

    def extract_card_specs(self, card):
        specs = []
        if m := re.search(r'vCPU[^0-9]*(\d+)|(\d+)\s*Core', card, re.I):
            specs.append(f"{m.group(1) or m.group(2)}C")
        if m := re.search(r'RAM[^0-9]*(\d+)', card, re.I):
            specs.append(f"{m.group(1)}G")
        if m := re.search(r'Disk[^0-9]*(\d+)|(\d+)GB\s*SSD', card, re.I):
            specs.append(f"{m.group(1) or m.group(2)}G")
        if m := re.search(r'([\d.]+)\s*TB', card, re.I):
            specs.append(f"{m.group(1)}T")
        return '/'.join(specs)

    def extract_card_stock(self, card):
        if '0 Available' in card or '0 available' in card:
            return False
        return True
