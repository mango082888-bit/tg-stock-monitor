#!/usr/bin/env python3
"""
TG Stock Monitor Bot
监控商品库存，自动发送补货通知
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv
from monitor import StockMonitor

load_dotenv()

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
PRODUCTS_FILE = os.path.join(DATA_DIR, 'products.json')
TARGETS_FILE = os.path.join(DATA_DIR, 'targets.json')
os.makedirs(DATA_DIR, exist_ok=True)

class StockBot:
    def __init__(self):
        self.token = os.getenv('BOT_TOKEN')
        self.admin_id = int(os.getenv('ADMIN_ID', '0'))
        self.products = self.load_json(PRODUCTS_FILE, [])
        self.targets = self.load_json(TARGETS_FILE, [])
        self.monitor = StockMonitor()
        self.check_interval = 30
        self.waiting_for = {}  # user_id -> action
        
    def load_json(self, path, default):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default
    
    def save_products(self):
        with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.products, f, ensure_ascii=False, indent=2)
    
    def save_targets(self):
        with open(TARGETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.targets, f, ensure_ascii=False, indent=2)
    
    def is_admin(self, user_id):
        return user_id == self.admin_id
    
    def get_main_menu(self):
        keyboard = [
            [InlineKeyboardButton("➕ 添加监控", callback_data="add"),
             InlineKeyboardButton("📋 监控列表", callback_data="list")],
            [InlineKeyboardButton("🎯 推送目标", callback_data="targets"),
             InlineKeyboardButton("🔗 绑定当前", callback_data="bind")],
            [InlineKeyboardButton("⏱ 检查频率", callback_data="interval"),
             InlineKeyboardButton("📊 运行状态", callback_data="status")]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ 无权限")
            return
        await update.message.reply_text(
            "🤖 **库存监控 Bot**\n\n请选择操作：",
            reply_markup=self.get_main_menu(),
            parse_mode='Markdown'
        )

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if not self.is_admin(query.from_user.id):
            return
        
        data = query.data
        
        if data == "add":
            self.waiting_for[query.from_user.id] = "add_url"
            await query.edit_message_text(
                "📝 请发送商品链接\n\n格式：`链接 [优惠码]`\n例如：`https://xxx.com/123 CODE20`",
                parse_mode='Markdown'
            )
        elif data == "list":
            await self.show_list(query)
        elif data == "targets":
            await self.show_targets(query)
        elif data == "bind":
            await self.bind_chat(query)
        elif data == "status":
            await self.show_status(query)
        elif data == "interval":
            await self.show_interval(query)
        elif data == "menu":
            await query.edit_message_text(
                "🤖 **库存监控 Bot**\n\n请选择操作：",
                reply_markup=self.get_main_menu(),
                parse_mode='Markdown'
            )
        elif data.startswith("del_"):
            pid = int(data.split("_")[1])
            await self.delete_product(query, pid)
        elif data.startswith("check_"):
            pid = int(data.split("_")[1])
            await self.check_product(query, pid)
        elif data.startswith("unbind_"):
            idx = int(data.split("_")[1])
            await self.unbind_target(query, idx)
        elif data.startswith("interval_"):
            sec = int(data.split("_")[1])
            self.check_interval = sec
            await query.edit_message_text(f"✅ 检查频率已设为 {sec} 秒", reply_markup=self.back_menu())

    def back_menu(self):
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回菜单", callback_data="menu")]])

    async def show_list(self, query):
        if not self.products:
            await query.edit_message_text("📭 暂无监控商品", reply_markup=self.back_menu())
            return
        
        msg = "📋 **监控列表**\n\n"
        keyboard = []
        for p in self.products:
            stock = '✅' if p.get('in_stock') else '❌'
            coupon = f" 🎫{p['coupon']}" if p.get('coupon') else ''
            msg += f"`{p['id']}` {stock} **{p['merchant']}**\n   {p['name']}{coupon}\n\n"
            keyboard.append([
                InlineKeyboardButton(f"🔍 检查 #{p['id']}", callback_data=f"check_{p['id']}"),
                InlineKeyboardButton(f"🗑 删除 #{p['id']}", callback_data=f"del_{p['id']}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 返回菜单", callback_data="menu")])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def show_targets(self, query):
        if not self.targets:
            await query.edit_message_text("📭 暂无推送目标\n\n在群/频道/私聊中点击「绑定当前」添加", reply_markup=self.back_menu())
            return
        
        msg = "🎯 **推送目标**\n\n"
        keyboard = []
        for i, t in enumerate(self.targets):
            msg += f"`{i+1}` {t.get('title', t['chat_id'])}\n"
            keyboard.append([InlineKeyboardButton(f"🗑 移除 #{i+1}", callback_data=f"unbind_{i}")])
        keyboard.append([InlineKeyboardButton("🔙 返回菜单", callback_data="menu")])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def bind_chat(self, query):
        chat = query.message.chat
        chat_id = chat.id
        
        for t in self.targets:
            if t['chat_id'] == chat_id:
                await query.edit_message_text("⚠️ 当前聊天已绑定", reply_markup=self.back_menu())
                return
        
        title = chat.title or chat.full_name or str(chat_id)
        self.targets.append({'chat_id': chat_id, 'title': title})
        self.save_targets()
        await query.edit_message_text(f"✅ 已绑定: {title}", reply_markup=self.back_menu())

    async def unbind_target(self, query, idx):
        if 0 <= idx < len(self.targets):
            removed = self.targets.pop(idx)
            self.save_targets()
            await query.edit_message_text(f"✅ 已移除: {removed.get('title')}", reply_markup=self.back_menu())
        else:
            await query.edit_message_text("❌ 目标不存在", reply_markup=self.back_menu())

    async def show_status(self, query):
        msg = f"""📊 **运行状态**

📦 监控商品: {len(self.products)} 个
🎯 推送目标: {len(self.targets)} 个
⏱ 检查频率: {self.check_interval} 秒"""
        await query.edit_message_text(msg, reply_markup=self.back_menu(), parse_mode='Markdown')

    async def show_interval(self, query):
        keyboard = [
            [InlineKeyboardButton("30秒", callback_data="interval_30"),
             InlineKeyboardButton("60秒", callback_data="interval_60")],
            [InlineKeyboardButton("120秒", callback_data="interval_120"),
             InlineKeyboardButton("300秒", callback_data="interval_300")],
            [InlineKeyboardButton("🔙 返回", callback_data="menu")]
        ]
        await query.edit_message_text(f"当前: {self.check_interval}秒\n选择新频率:", reply_markup=InlineKeyboardMarkup(keyboard))

    async def delete_product(self, query, pid):
        for i, p in enumerate(self.products):
            if p['id'] == pid:
                removed = self.products.pop(i)
                self.save_products()
                await query.edit_message_text(f"✅ 已删除: {removed['name']}", reply_markup=self.back_menu())
                return
        await query.edit_message_text("❌ 未找到", reply_markup=self.back_menu())

    async def check_product(self, query, pid):
        for p in self.products:
            if p['id'] == pid:
                await query.edit_message_text("🔍 正在检查...")
                info = await self.monitor.parse_product(p['url'])
                if info:
                    p['in_stock'] = info.get('in_stock', False)
                    p['price'] = info.get('price', p['price'])
                    p['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    self.save_products()
                    stock = '有货 ✅' if p['in_stock'] else '无货 ❌'
                    msg = f"📊 **检查结果**\n\n商品: {p['name']}\n价格: {p['price']}\n状态: {stock}"
                    await query.edit_message_text(msg, reply_markup=self.back_menu(), parse_mode='Markdown')
                else:
                    await query.edit_message_text("❌ 检查失败", reply_markup=self.back_menu())
                return
        await query.edit_message_text("❌ 未找到", reply_markup=self.back_menu())

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            return
        
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        if user_id in self.waiting_for and self.waiting_for[user_id] == "add_url":
            del self.waiting_for[user_id]
            parts = text.split(maxsplit=1)
            url = parts[0]
            coupon = parts[1] if len(parts) > 1 else None
            
            await update.message.reply_text("🔍 正在解析...")
            info = await self.monitor.parse_product(url)
            
            if not info:
                await update.message.reply_text("❌ 无法解析", reply_markup=self.back_menu())
                return
            
            pid = max([p['id'] for p in self.products], default=0) + 1
            product = {
                'id': pid, 'url': url,
                'name': info.get('name', '未知'),
                'merchant': info.get('merchant', '未知'),
                'price': info.get('price', '未知'),
                'specs': info.get('specs', ''),
                'coupon': coupon,
                'in_stock': info.get('in_stock', False),
                'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            self.products.append(product)
            self.save_products()
            
            stock = '有货 ✅' if product['in_stock'] else '无货 ❌'
            msg = f"✅ **添加成功**\n\n🏪 {product['merchant']}\n📦 {product['name']}\n💰 {product['price']}\n🎫 {coupon or '无'}\n📊 {stock}\n🔢 编号: {pid}"
            await update.message.reply_text(msg, reply_markup=self.back_menu(), parse_mode='Markdown')

    async def notify(self, app, product, is_restock):
        """发送通知"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if is_restock:
            tag = "#补货通知"
            status = "✅ 有货"
        else:
            tag = "#无货"
            status = "❌ 无货"
        
        coupon_line = f"🎫 优惠码: `{product['coupon']}`\n" if product.get('coupon') else ""
        specs_line = f"⚙️ {product['specs']}\n" if product.get('specs') else ""
        
        msg = f"""#库存监控 {tag}

**{product['merchant']}**
{product['name']}
💰 {product['price']}
{specs_line}{coupon_line}
🔗 [直接购买]({product['url']})

{now} {status}"""
        
        for t in self.targets:
            try:
                await app.bot.send_message(
                    chat_id=t['chat_id'], 
                    text=msg, 
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"发送失败 {t}: {e}")

    async def monitor_loop(self, app):
        """定时检查库存"""
        await asyncio.sleep(5)
        while True:
            for p in self.products:
                try:
                    info = await self.monitor.parse_product(p['url'])
                    if info:
                        was_in = p.get('in_stock', False)
                        now_in = info.get('in_stock', False)
                        
                        p['in_stock'] = now_in
                        p['price'] = info.get('price', p['price'])
                        p['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                        if not was_in and now_in:
                            await self.notify(app, p, True)
                            logger.info(f"补货: {p['name']}")
                        elif was_in and not now_in:
                            await self.notify(app, p, False)
                            logger.info(f"缺货: {p['name']}")
                        
                        self.save_products()
                except Exception as e:
                    logger.error(f"检查失败 {p.get('name')}: {e}")
                await asyncio.sleep(3)
            await asyncio.sleep(self.check_interval)

def main():
    bot = StockBot()
    app = Application.builder().token(bot.token).build()
    
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(CommandHandler("help", bot.start))
    app.add_handler(CallbackQueryHandler(bot.button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(bot.monitor_loop(app))
    
    logger.info("Bot 启动")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
