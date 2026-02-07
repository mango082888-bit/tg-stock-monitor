# TG Stock Monitor

Telegram 商品库存监控 Bot，自动检测补货并发送通知。

## 功能

- 添加商品链接自动识别商家、名称、价格
- 定时检测库存状态
- 补货自动通知到频道
- 支持设置优惠码
- 多频道推送

## 部署

```bash
# 安装依赖
pip install -r requirements.txt

# 配置
cp .env.example .env
# 编辑 .env 填写 BOT_TOKEN 和 ADMIN_ID

# 运行
python bot.py
```

## 命令

**商品管理：**
- `/add <链接> [优惠码]` - 添加监控
- `/list` - 查看列表
- `/del <编号>` - 删除
- `/edit <编号> code <优惠码>` - 修改优惠码
- `/check <编号>` - 立即检查

**频道管理：**
- `/add_channel <频道>` - 添加频道
- `/list_channels` - 查看频道
- `/del_channel <编号>` - 删除频道
