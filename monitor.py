#!/usr/bin/env python3
"""商品页面解析模块 - 使用 Playwright 浏览器抓取"""

import re
import asyncio
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# Misaka 所有地区
MISAKA_LOCATIONS = [
    ('sin03', 'Singapore SIN03'),
    ('nrt04', 'Tokyo NRT04'),
    ('hkg12', 'Hong Kong HKG12'),
    ('tpe01', 'Taipei TPE01'),
]

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
            domain = urlparse(url).netloc
            if 'misaka' in domain:
                await asyncio.sleep(5)
            else:
                await asyncio.sleep(2)
            html = await page.content()
            await page.close()
            return html
        except Exception as e:
            print(f"Fetch error: {e}")
            return None

    async def parse_product(self, url):
        domain = urlparse(url).netloc
        
        # Misaka: 返回所有地区列表
        if 'misaka' in domain:
            return await self.parse_misaka_all(url)
        
        html = await self.fetch(url)
        if not html:
            return None
        
        if self.is_category_page(html):
            return await self.parse_category(html, url, domain)
        
        return {
            'merchant': self.get_merchant(html, domain, url),
            'name': self.get_name(html, url),
            'price': self.get_price(html),
            'specs': self.get_specs(html),
            'in_stock': self.check_stock(html)
        }
    
    async def parse_misaka_all(self, url):
        """解析 Misaka 所有地区"""
        # 从 URL 提取 plan: /iaas/vm/create/hkg12/s3n-1c1g
        parts = url.rstrip('/').split('/')
        plan = parts[-1] if len(parts) >= 1 else 's3n-1c1g'
        
        products = []
        for loc_code, loc_name in MISAKA_LOCATIONS:
            loc_url = f"https://app.misaka.io/iaas/vm/create/{loc_code}/{plan}"
            html = await self.fetch(loc_url)
            if html:
                info = self.parse_misaka_single(html, loc_url, loc_code, loc_name, plan)
                info['url'] = loc_url
                products.append(info)
        
        return products if products else None
    
    def parse_misaka_single(self, html, url, loc_code, loc_name, plan):
        """解析单个 Misaka 地区"""
        # 解析配置 s3n-1c1g
        specs = ''
        m = re.search(r'(\d+)c(\d+)g', plan, re.I)
        if m:
            specs = f"{m.group(1)}C/{m.group(2)}G"
        
        # 价格
        price = 'price unknown'
        for p in [r'HK\$\s*([\d.]+)', r'\$\s*([\d.]+)\s*/\s*mo', r'\$\s*([\d.]+)']:
            m = re.search(p, html, re.I)
            if m:
                price = f"HK${m.group(1)}/mo"
                break
        
        # 库存
        in_stock = True
        html_lower = html.lower()
        if 'out of stock' in html_lower or 'out_of_stock' in html_lower:
            in_stock = False
        if 'sold out' in html_lower or 'currently unavailable' in html_lower:
            in_stock = False
        
        return {
            'merchant': 'Misaka',
            'name': f"{loc_name} {plan}",
            'price': price,
            'specs': specs,
            'in_stock': in_stock
        }

    def is_category_page(self, html):
        cards = re.findall(r'class="[^"]*package[^"]*"', html, re.I)
        return len(cards) > 1
    
    def get_merchant(self, html, domain, url):
        name = domain.replace('my.', '').replace('www.', '').replace('app.', '').split('.')[0]
        return name.upper()

    def get_name(self, html, url):
        if '/store/' in url:
            name = url.split('/')[-1].split('?')[0]
            return name.replace('-', ' ').title()[:50]
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        if m:
            return m.group(1).strip()[:50]
        return "Unknown"

    def get_price(self, html):
        patterns = [
            r'\$(\d+\.?\d*)\s*USD\s*Monthly',
            r'\$(\d+\.?\d*)\s*USD',
            r'Starting from[^$]*\$(\d+\.?\d*)',
        ]
        for p in patterns:
            m = re.search(p, html, re.I)
            if m:
                return f"${m.group(1)}/mo"
        return "price unknown"

    def get_specs(self, html):
        specs = []
        m = re.search(r'vCPU\s*(?:Core\s*)?(\d+)|(\d+)\s*Core', html, re.I)
        if m:
            specs.append(f"{m.group(1) or m.group(2)}C")
        m = re.search(r'RAM\s*(\d+)\s*GB|(\d+)\s*GB\s*RAM', html, re.I)
        if m:
            specs.append(f"{m.group(1) or m.group(2)}G")
        m = re.search(r'Disk\s*(\d+)\s*GB|(\d+)\s*GB\s*SSD', html, re.I)
        if m:
            specs.append(f"{m.group(1) or m.group(2)}G")
        return '/'.join(specs) if specs else ""

    def check_stock(self, html):
        html_lower = html.lower()
        for kw in ['0 available', 'out of stock', 'sold out']:
            if kw in html_lower:
                return False
        return True

    async def parse_category(self, html, url, domain):
        products = []
        merchant = self.get_merchant(html, domain, url)
        pattern = r'<div[^>]*class="[^"]*package[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>'
        cards = re.findall(pattern, html, re.S | re.I)
        
        for card in cards:
            name = self.extract_card_name(card)
            if name:
                products.append({
                    'merchant': merchant,
                    'name': name,
                    'price': self.extract_card_price(card),
                    'specs': self.extract_card_specs(card),
                    'in_stock': self.extract_card_stock(card)
                })
        return products if products else None

    def extract_card_name(self, card):
        m = re.search(r'<h[23][^>]*>([^<]+)</h[23]>', card, re.I)
        return m.group(1).strip()[:50] if m else None

    def extract_card_price(self, card):
        m = re.search(r'\$(\d+\.?\d*)', card)
        return f"${m.group(1)}/mo" if m else "price unknown"

    def extract_card_specs(self, card):
        specs = []
        if m := re.search(r'vCPU[^0-9]*(\d+)|(\d+)\s*Core', card, re.I):
            specs.append(f"{m.group(1) or m.group(2)}C")
        if m := re.search(r'RAM[^0-9]*(\d+)', card, re.I):
            specs.append(f"{m.group(1)}G")
        return '/'.join(specs)

    def extract_card_stock(self, card):
        if '0 Available' in card or '0 available' in card:
            return False
        return True
