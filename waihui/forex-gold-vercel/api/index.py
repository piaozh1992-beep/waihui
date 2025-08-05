import os
import re
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
import asyncio
from pyppeteer import launch
from pyppeteer.errors import TimeoutError

# 初始化Flask应用
app = Flask(__name__)
CORS(app)  # 允许跨域（小程序调用必需）

# 轻量级浏览器配置（适配Vercel环境）
async def init_browser():
    """初始化pyppeteer浏览器（替代Selenium）"""
    return await launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--single-process",
        ],
        executablePath="/usr/bin/chromium-browser"  # Vercel容器中的Chromium路径
    )

async def extract_numbers(text):
    """提取纯数字"""
    if not text:
        return ""
    numbers = re.findall(r'\d+\.?\d*', text)
    return numbers[0] if numbers else ""

async def scrape_forex():
    """爬取外汇数据（招商银行）"""
    browser = await init_browser()
    page = await browser.newPage()
    forex_data = []
    
    try:
        await page.goto("https://fx.cmbchina.com/", timeout=8000)
        await page.waitForSelector("table", timeout=5000)  # 等待表格加载
        
        # 提取1-10行数据
        for i in range(1, 11):
            try:
                # 使用CSS选择器提取（比XPath更稳定）
                currency_selector = f"table tbody tr:nth-child({i}) td:nth-child(1)"
                rate_selector = f"table tbody tr:nth-child({i}) td:nth-child(4)"
                
                currency = await page.evaluate(f'''() => {{
                    const el = document.querySelector('{currency_selector}');
                    return el ? el.textContent.trim() : '';
                }}''')
                
                rate = await page.evaluate(f'''() => {{
                    const el = document.querySelector('{rate_selector}');
                    return el ? el.textContent.trim() : '';
                }}''')
                
                forex_data.append({"category": currency, "price": rate})
            except:
                forex_data.append({"category": f"未找到数据_{i}", "price": ""})
                
    except Exception as e:
        print(f"外汇爬取失败: {str(e)}")
    finally:
        await browser.close()
    
    return forex_data

async def scrape_gold():
    """爬取黄金数据（建设银行）"""
    browser = await init_browser()
    page = await browser.newPage()
    gold_data = {"category": "黄金价格", "price": ""}
    
    try:
        await page.goto("https://www2.ccb.com/chn/home/gold_new/gjssy/index.shtml", timeout=8000)
        await page.waitForSelector("div", timeout=5000)
        
        # 提取黄金价格（模糊匹配）
        gold_text = await page.evaluate('''() => {
            const elements = document.querySelectorAll('div');
            for (let el of elements) {
                if (el.textContent.includes('黄金') && el.nextElementSibling) {
                    return el.nextElementSibling.textContent.trim();
                }
            }
            return '';
        }''')
        
        gold_price = await extract_numbers(gold_text)
        gold_data["price"] = gold_price
        
    except Exception as e:
        print(f"黄金爬取失败: {str(e)}")
    finally:
        await browser.close()
    
    return gold_data

# Vercel Serverless函数入口（必选）
@app.route('/api/get_data', methods=['GET'])
def handler():
    """处理小程序请求，实时爬取数据"""
    try:
        # 同步运行异步函数
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        forex_data = loop.run_until_complete(scrape_forex())
        gold_data = loop.run_until_complete(scrape_gold())
        
        return jsonify({
            "code": 200,
            "message": "success",
            "data": {
                "forex": forex_data,
                "gold": gold_data,
                "update_time": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        })
        
    except Exception as e:
        return jsonify({
            "code": 500,
            "message": f"获取失败: {str(e)}",
            "data": None
        })

# 本地测试用（Vercel部署时会忽略）
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
