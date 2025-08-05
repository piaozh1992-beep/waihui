from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from flask import Flask, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import time
import re
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 初始化Flask应用
app = Flask(__name__)
CORS(app)  # 解决跨域问题

# 全局变量存储最新数据
latest_data = {
    "forex": [],  # 外汇数据
    "gold": {"category": "黄金价格", "price": ""},  # 黄金数据
    "update_time": ""  # 更新时间
}

def init_driver():
    """初始化无头浏览器"""
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")  # 最新无头模式
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36")
        
        # 尝试不同的ChromeDriver路径，增加兼容性
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except:
            # 尝试常见的ChromeDriver路径
            driver = webdriver.Chrome(executable_path='/usr/local/bin/chromedriver', options=chrome_options)
            
        driver.implicitly_wait(10)
        return driver
    except Exception as e:
        logger.error(f"初始化浏览器失败: {str(e)}")
        return None

def extract_numbers(text):
    """从文本中提取数字"""
    if not text:
        return ""
    numbers = re.findall(r'\d+\.?\d*', text)
    return numbers[0] if numbers else ""

def scrape_all_data():
    """爬取所有数据并更新全局变量"""
    global latest_data
    logger.info("开始爬取数据...")
    
    driver = init_driver()
    if not driver:
        logger.error("无法初始化浏览器，爬取失败")
        return False
    
    try:
        # 爬取网站1外汇数据
        forex_data = []
        driver.get("https://fx.cmbchina.com/")
        time.sleep(3)
        
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="root"]/div/div[3]/div/div/div[2]/div/div[2]/div[2]/table'))
            )
            
            for i in range(1, 11):
                try:
                    currency = driver.find_element(By.XPATH, f'//*[@id="root"]/div/div[3]/div/div/div[2]/div/div[2]/div[2]/table/tbody/tr[{i}]/td[1]').text.strip()
                    rate = driver.find_element(By.XPATH, f'//*[@id="root"]/div/div[3]/div/div/div[2]/div/div[2]/div[2]/table/tbody/tr[{i}]/td[4]').text.strip()
                    forex_data.append({"category": currency, "price": rate})
                    logger.info(f"爬取外汇数据: {currency} - {rate}")
                except:
                    forex_data.append({"category": f"未找到数据_{i}", "price": ""})
                    logger.warning(f"外汇数据第{i}条爬取失败")
        except Exception as e:
            logger.error(f"网站1爬取失败: {str(e)}")
        
        # 爬取网站2黄金数据
        gold_price = ""
        driver.get("https://www2.ccb.com/chn/home/gold_new/gjssy/index.shtml")
        time.sleep(3)
        
        try:
            # 尝试原始XPath
            gold_text = driver.find_element(By.XPATH, '//*[@id="16fe3be325f647d894edb0008a00e44d"]/div[2]/div/div[2]/div[1]/div[1]/div[1]').text.strip()
        except:
            # 备用路径
            try:
                gold_elements = driver.find_elements(By.XPATH, '//div[contains(text(), "黄金")]/following-sibling::div')
                gold_text = gold_elements[0].text.strip() if gold_elements else ""
            except:
                gold_text = ""
        
        gold_price = extract_numbers(gold_text)
        logger.info(f"爬取黄金价格: {gold_price}")
        
        # 更新全局数据（覆盖原有数据）
        latest_data = {
            "forex": forex_data,
            "gold": {"category": "黄金价格", "price": gold_price},
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        logger.info("数据更新成功")
        return True
        
    except Exception as e:
        logger.error(f"爬取过程出错: {str(e)}")
        return False
    finally:
        if driver:
            driver.quit()

# API接口：获取最新数据
@app.route('/api/get_data', methods=['GET'])
def get_data():
    """提供给微信小程序的API接口"""
    try:
        # 如果从未更新过数据，立即爬取一次
        if not latest_data["update_time"]:
            scrape_all_data()
            
        return jsonify({
            "code": 200,
            "message": "success",
            "data": latest_data
        })
    except Exception as e:
        return jsonify({
            "code": 500,
            "message": f"获取数据失败: {str(e)}",
            "data": None
        })

def init_scheduler():
    """初始化定时任务"""
    scheduler = BackgroundScheduler(timezone='Asia/Shanghai')  # 使用北京时间
    
    # 添加定时任务：每15分钟运行一次，从整点开始（0分、15分、30分、45分）
    scheduler.add_job(
        func=scrape_all_data,
        trigger='cron',
        minute='0,15,30,45',  # 整点、15分、30分、45分执行
        id='forex_gold_job',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("定时任务已启动，将在每小时的0分、15分、30分、45分运行")
    return scheduler

if __name__ == "__main__":
    # 初始化定时任务
    scheduler = init_scheduler()
    
    try:
        # 启动时立即爬取一次数据
        scrape_all_data()
        
        # 启动Flask服务
        logger.info("API服务启动中...")
        logger.info("访问地址: http://localhost:5000/api/get_data")
        logger.info("微信小程序可通过服务器IP访问，如: http://your-server-ip:5000/api/get_data")
        
        # 生产环境应关闭debug，此处为了开发方便保留
        app.run(host='0.0.0.0', port=5000, debug=False)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("程序已退出")
    