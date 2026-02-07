#!/usr/bin/env python3
"""商品页面解析模块 - 支持 WHMCS 等 VPS 商家"""

import re
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

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
        
        # 检测是否是 WHMCS 系统
        is_whmcs = 'whmcs' in html.lower() or '/store/' in url or '/cart.php' in url
        
        if is_whmcs:
            return self.parse_whmcs(soup, domain, url, html)
        
        return {
            'merchant': self.get_merchant(soup, domain),
            'name': self.get_name(soup),
            'price': self.get_price(soup, html),
            'specs': self.get_specs(soup, html),
            'in_stock': self.check_stock(soup, html)
        }

    def parse_whmcs(self, soup, domain, url, html):
        """解析 WHMCS 商品页面"""
        merchant = domain.replace('my.', '').replace('www.', '').split('.')[0].upper()
        
        # 从 URL 提取商品名
        name = "未知商品"
        if '/store/' in url:
            parts = url.split('/')
            for i, p in enumerate(parts):
                if p == 'store' and i + 1 < len(parts):
                    name = parts[-1] if parts[-1] else parts[-2]
                    name = name.split('?')[0].replace('-', ' ').title()[:50]
                    break
        
        # 查找商品卡片
        products = []
        cards = soup.find_all('div', class_=re.compile(r'product|package|plan', re.I))
        
        for card in cards:
            text = card.get_text()
            # 提取价格
            price_match = re.search(r'\$(\d+\.?\d*)\s*USD', text)
            price = f"${price_match.group(1)}" if price_match else None
            
            # 提取配置
            specs = self.extract_whmcs_specs(text)
            
            # 检查库存
            avail_match = re.search(r'(\d+)\s*Available', text)
            in_stock = True
            if avail_match:
                in_stock = int(avail_match.group(1)) > 0
            elif '0 Available' in text or 'Out of Stock' in text.title():
                in_stock = False
            
            if price:
                products.append({
                    'price': price,
                    'specs': specs,
                    'in_stock': in_stock
                })
        
        # 取第一个有效商品
        if products:
            p = products[0]
            return {
                'merchant': merchant,
                'name': name,
                'price': p['price'],
                'specs': p['specs'],
                'in_stock': p['in_stock']
            }
        
        # 回退到通用解析
        return {
            'merchant': merchant,
            'name': name,
            'price': self.get_price(soup, html),
            'specs': self.get_specs(soup, html),
            'in_stock': self.check_stock(soup, html)
        }

    def extract_whmcs_specs(self, text):
        """从 WHMCS 卡片提取配置"""
        specs = []
        
        # vCPU
        cpu = re.search(r'vCPU\s*(?:Core\s*)?(\d+)|(\d+)\s*vCPU|(\d+)\s*Core', text, re.I)
        if cpu:
            c = cpu.group(1) or cpu.group(2) or cpu.group(3)
            specs.append(f"{c}C")
        
        # RAM
        ram = re.search(r'RAM\s*(\d+)\s*GB|(\d+)\s*GB\s*RAM|(\d+)G\s*内存', text, re.I)
        if ram:
            r = ram.group(1) or ram.group(2) or ram.group(3)
            specs.append(f"{r}G")
        
        # Disk
        disk = re.search(r'Disk\s*(\d+)\s*GB|(\d+)\s*GB\s*SSD|SSD\s*(\d+)\s*GB', text, re.I)
        if disk:
            d = disk.group(1) or disk.group(2) or disk.group(3)
            specs.append(f"{d}G")
        
        # Traffic
        traffic = re.search(r'Traffic\s*([\d.]+)\s*TB|(\d+)\s*TB\s*流量|([\d.]+)T\s*流量', text, re.I)
        if traffic:
            t = traffic.group(1) or traffic.group(2) or traffic.group(3)
            specs.append(f"{t}T")
        
        return '/'.join(specs) if specs else ""

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
            r'\$(\d+\.?\d*)\s*USD',
            r'[\$¥￥]\s*(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*/月',
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
        ]
        for p in patterns:
            m = re.search(p, html, re.I)
            if m:
                return m.group(1)
        return ""
    
    def check_stock(self, soup, html):
        html_lower = html.lower()
        out_kw = ['out of stock', 'sold out', '0 available', '缺货', '售罄']
        for kw in out_kw:
            if kw in html_lower:
                return False
        in_kw = ['in stock', 'add to cart', 'order now', '有货']
        for kw in in_kw:
            if kw in html_lower:
                return True
        return True
