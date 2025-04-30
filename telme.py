import requests
import configparser
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime
import logging
import time
from bs4 import BeautifulSoup

logging.basicConfig(filename='bot.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

config = configparser.ConfigParser()
config.read('config.ini')

bot_token = config.get('telegram', 'bot_token')
chat_id = config.get('telegram', 'chat_id')

alert_triggered = False
last_alert_time = None
monitoring_job_eth = None
monitoring_job_web = None
previous_value = None

def get_eth_price():
    retries = 99999999999999999999999
    for _ in range(retries):
        try:
            url = "https://www.okx.com/api/v5/market/ticker?instId=ETH-USDT"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data['code'] == '0':
                price = data['data'][0]['last']
                return int(float(price))
        except requests.exceptions.Timeout:
            logging.warning("Request timed out, retrying...")
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error: {e}")
        time.sleep(5)
    return None

async def send_price_alert(context: ContextTypes.DEFAULT_TYPE) -> None:
    global alert_triggered, last_alert_time
    current_time = datetime.now()
    if alert_triggered and (current_time - last_alert_time).seconds < 600:
        return
    price = get_eth_price()
    if price is None:
        return
    if price > 3000:
        await context.bot.send_message(chat_id=chat_id, text="up")
        alert_triggered = True
        last_alert_time = current_time
    elif price < 1500:
        await context.bot.send_message(chat_id=chat_id, text="down")
        alert_triggered = True
        last_alert_time = current_time
    else:
        alert_triggered = False

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    price = get_eth_price()
    if price is None:
        await update.message.reply_text("Failed to fetch data, please try again later.")
    else:
        await update.message.reply_text(f"{price}")

def get_web_element():
    retries = 99999999999999999999999
    for _ in range(retries):
        try:
            url = "https://web3.okx.com/zh-hans/explorer/bsc/address/0xeba6ad75e46406cc6b6ce9c8ac6c431fef493e5b/event"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            element = soup.select_one('div#root > main > div > div > div:nth-of-type(3) > div > div:nth-of-type(2) > div > div')
            if element:
                return element.get_text(strip=True)
        except requests.exceptions.Timeout:
            logging.warning("Request timed out, retrying...")
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error: {e}")
        time.sleep(5)
    return None

async def check_web_change(context: ContextTypes.DEFAULT_TYPE) -> None:
    global previous_value
    current_value = get_web_element()
    if current_value is None:
        return
    if current_value != previous_value:
        await context.bot.send_message(chat_id=chat_id, text=f"TG")
        previous_value = current_value

async def start_eth_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global monitoring_job_eth
    job_queue = context.application.job_queue
    if monitoring_job_eth is not None:
        monitoring_job_eth.schedule_removal()
    monitoring_job_eth = job_queue.run_repeating(send_price_alert, interval=5, first=0)
    await update.message.reply_text("s monitoring started")

async def start_web_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global monitoring_job_web, previous_value
    job_queue = context.application.job_queue
    if monitoring_job_web is not None:
        monitoring_job_web.schedule_removal()
    previous_value = get_web_element()
    monitoring_job_web = job_queue.run_repeating(check_web_change, interval=30, first=0)
    await update.message.reply_text("w monitoring started")

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    eth_status = "Started" if monitoring_job_eth else "Not started"
    web_status = "Started" if monitoring_job_web else "Not started"
    await update.message.reply_text(f"/h help\n"
                                   f"/w w monitoring status: {web_status}\n"
                                   f"/s s monitoring status: {eth_status}\n"
                                   f"/p Instant query")

def main():
    while True:
        try:
            application = Application.builder().token(bot_token).build()
            application.add_handler(CommandHandler("p", price))
            application.add_handler(CommandHandler("s", start_eth_monitoring))
            application.add_handler(CommandHandler("w", start_web_monitoring))
            application.add_handler(CommandHandler("h", help))
            application.run_polling()
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            print("An error occurred, restarting...")
            continue

if __name__ == '__main__':
    main()
