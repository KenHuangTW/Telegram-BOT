# 目標: 在每天的早上7點30分寄送有關於美股大盤指數的收盤價，以及是否跌破均線
# 注意美國與台灣的時差
import time  # 休息用
from telegram.ext import Updater  # 訊息用
from telegram.ext import CommandHandler  # 指令
import logging  # 紀錄
import yfinance as yf  # 取得股市資料
import datetime as dt  # 使用時間
from pytz import timezone  # 處理時區問題
import mplfinance as mpf  # 繪製k線圖
from bs4 import BeautifulSoup  # 解析HTML檔案
import urllib.request as req  # 爬取新聞
import ssl  # 憑證問題

token = "Your Token"
updater = Updater(token=token, use_context=True)  # 更新使用者訊息
dispatcher = updater.dispatcher
job = updater.job_queue
a = "、"  # 等等要給join用的
taiwan = timezone("Asia/Taipei")  # 時區裡面是台北，沒有台灣

# 紀錄錯誤訊息
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)


def start(update, context):
    context.bot.send_message(chat_id="your id", text="您好，我是美股咕咕鐘"
                                                                    "我會在每天的早上7點30分提供美國股市的大盤指數")


def up_down(today: list, yesterday: list) -> dict:  # 處理上漲以及下跌
    up_result = []  # 用list，後面寫 format比較好寫
    # today[0], yesterday[0] is int
    close = round(today[0] - yesterday[0], 2)
    if close > 0:
        up_result.append("上漲")
    elif close < 0:
        up_result.append("下跌")
    elif close == 0:
        up_result.append("平盤")
        return up_result
    up_result.append(close)
    return up_result


def ma_calculate(today, ma_5: list, ma_10: list, ma_20: list, ma_60: list) -> dict:
    # 目的: 計算均線，便於觀察是壓力或是支撐
    # today[0] 是 int
    result_ma_5 = round(sum(ma_5), 2) / 5
    result_ma_10 = round(sum(ma_10), 2) / 10
    result_ma_20 = round(sum(ma_20), 2) / 20
    result_ma_60 = round(sum(ma_60), 2) / 60
    ma_result = dict()
    ma_up = []
    ma_down = []
    ma_same = []
    all_ma = {"5日均線": result_ma_5, "10日均線": result_ma_10, "20日均線": result_ma_20, "60日均線": result_ma_60}
    for key, value in all_ma.items():
        if today[0] > value:
            ma_up.append(key)
            ma_result["站上"] = ma_up
        elif today[0] == value:
            ma_same.append(key)
            ma_result["貼齊"] = ma_same
        elif today[0] < value:
            ma_down.append(key)
            ma_result["跌破"] = ma_down
    ma_result.setdefault("站上", ["沒有"])  # 避免後續抓不到以及方便排版
    ma_result.setdefault("跌破", ["沒有"])  # 避免後續抓不到以及方便排版
    ma_result.setdefault("貼齊", ["沒有"])  # 避免後續抓不到以及方便排版
    return ma_result


def pressure(range_20days: list) -> dict or str:  # 目的: 處理近期高低點，需顯示哪一天的最高點沒有突破
    pressure_result = []  # 方便顯示
    vs = 0
    for value, dd in zip(range_20days, range_20days.index):
        if value > vs:
            da_te = dt.datetime.date(dd)  # 取出日期
            da_te = dt.date.strftime(da_te, "%Y-%m-%d")  # 顯示用
            highest = value  # 取出點數
        if value < vs:  # 只儲存最大的
            continue
        vs = value  # 儲存
    pressure_result.append(da_te)
    pressure_result.append(highest)
    return pressure_result


def support(range_20days):  # 計算支撐
    support_result = []
    vs = 50000000
    for value, dd in zip(range_20days, range_20days.index):
        if value < vs:
            da_te = dt.datetime.date(dd)  # 取出日期
            da_te = dt.date.strftime(da_te, "%Y-%m-%d")  # 顯示用
            lowest = value  # 取出點數
        if value > vs:  # 只儲存最低的
            continue
        vs = value  # 儲存
    support_result.append(da_te)
    support_result.append(lowest)
    return support_result


def condition(ma_dict):  # 記錄各種情況
    ma_result = []
    if "沒有" in ma_dict["跌破"]:
        ma_result.append("非常強勢")
        ma_result.append("只要不跌破下方均線，短期內非常有可能持續向上噴發")
    elif (["5日均線"] == ma_dict["跌破"]) and (["10日均線", "20日均線", "60日均線"] == ma_dict["站上"]):
        ma_result.append("相對強勢")
        ma_result.append(f"要持續向上要把{a.join(ma_dict.get('跌破'))}站回且突破，若跌破十日則要開始一段比較長的整理了")
    elif (["5日均線", "10日均線"] == ma_dict["跌破"]) and (["20日均線", "60日均線"] == ma_dict["站上"]):
        ma_result.append("整理")
        ma_result.append("目前需要一段長時間的整理，注意月均線不可以跌破")
    elif (["5日均線", "10日均線", "20日均線"] == ma_dict["跌破"]) and (["60日均線"] == ma_dict["站上"]):
        ma_result.append("相對弱勢")
        ma_result.append("目前已跌破月線，極有可能持續往季線修正")
    elif ["沒有"] == ma_dict["站上"]:
        ma_result.append("非常弱勢")
        ma_result.append("已經全面翻空")
    elif ["5日均線"] or ["10日均線"] == ma_dict["站上"] and ["20日均線", "60日均線"] in ma_dict["跌破"]:
        ma_result.append("短線止跌")
        ma_result.append(f"注意{a.join(ma_dict['站上'])}不可跌破，否則會續跌")
    elif (["5日均線", "10日均線", "20日均線"] or ["5日均線", "10日均線", "60日均線"] == ma_dict) and (["20日均線"] or ["60日均線"] == ma_dict):
        ma_result.append("短線翻多")
        ma_result.append(f"上方只剩下{a.join(ma_dict.get('跌破'))}需要突破，只要不把{a.join(ma_dict.get('站上'))}跌破都有機會向上")
    return ma_result


def support_or_pressure(today, high_20days, low_20days, ma_result):  # 判斷附近支撐或壓力
    s_or_p_result = []  # support_or_pressure
    if (ma_result[0] == "非常強勢") and (today[0] < high_20days[1]):
        s_or_p_result.append(f"，但在{high_20days[0]} 還有壓力，需要特別注意")
    elif (ma_result[0] == "非常弱勢") and (today[0] > low_20days[1]):
        s_or_p_result.append(f"，但在{low_20days[0]} 還有支撐，可以稍微期待，但仍不建議短線投資進場")
    else:
        s_or_p_result.append("，高點的支撐與低點的壓力目前不太是重點")
    return s_or_p_result


def auto_download_and_send(context):  # 一定要下，不然run_daily不能跑
    now = dt.datetime.now()
    any_day = dt.date.today() - dt.timedelta(days=120)  # 找一個範圍大一點的數字，避免假日沒有開盤

    # 取得資料
    dow = yf.download("^DJI", start=any_day, end=now, group_by="ticker")
    nas = yf.download("^IXIC", start=any_day, end=now, group_by="ticker")
    phlx = yf.download("^SOX", start=any_day, end=now, group_by="ticker")
    dow_today = dow[-1:]["Close"]  # 此處沒有打索引，所以不會是 int
    nas_today = nas[-1:]["Close"]  # 此處沒有打索引，所以不會是 int
    phlx_today = phlx[-1:]["Close"]  # 此處沒有打索引，所以不會是 int

    # 這邊處理收盤結果 以及 上漲或是下跌
    up_dow = up_down(dow_today, dow[-2:-1]["Close"])
    up_nas = up_down(nas_today, nas[-2:-1]["Close"])
    up_phlx = up_down(phlx_today, phlx[-2:-1]["Close"])

    # 觀察收盤價是站上均線或跌破均線
    dow_ma = ma_calculate(dow_today, dow[-5:]["Close"], dow[-10:]["Close"], dow[-20:]["Close"], dow[-60:]["Close"])
    nas_ma = ma_calculate(nas_today, nas[-5:]["Close"], nas[-10:]["Close"], nas[-20:]["Close"], nas[-60:]["Close"])
    phlx_ma = ma_calculate(phlx_today, phlx[-5:]["Close"], phlx[-10:]["Close"],
                           phlx[-20:]["Close"], phlx[-60:]["Close"])

    # 以下計算近期高點是否未突破
    high_dow = pressure(dow[-20:]["High"])
    high_nas = pressure(nas[-20:]["High"])
    high_phlx = pressure(phlx[-20:]["High"])

    # 以下計算支撐
    low_dow = support(dow[-20:]["Low"])
    low_nas = support(nas[-20:]["Low"])
    low_phlx = support(phlx[-20:]["Low"])

    # 以下記錄狀況
    situation_dow = condition(dow_ma)
    situation_nas = condition(nas_ma)
    situation_phlx = condition(phlx_ma)

    # 判斷狀況
    judge_dow = support_or_pressure(dow_today, high_dow, low_dow, situation_dow)
    judge_nas = support_or_pressure(nas_today, high_nas, low_nas, situation_nas)
    judge_phlx = support_or_pressure(phlx_today, high_phlx, low_phlx, situation_phlx)

    # 繪製k線圖
    k_color = mpf.make_marketcolors(up='r', down='g', edge='', wick='inherit')  # 設定上漲下跌的k棒顏色
    style = mpf.make_mpf_style(base_mpf_style='yahoo', marketcolors=k_color, y_on_right=False)  # 等等要丟到顯示的參數
    # 以下皆用儲存圖片的方式
    mpf.plot(dow, title="DJIA", type='candle', mav=(5, 10, 20, 60), style=style,
             savefig=r"/home/wtf81905/dow.png")
    mpf.plot(nas, title="NASDAQ", type='candle', mav=(5, 10, 20, 60), style=style,
             savefig=r"/home/wtf81905/nas.png")
    mpf.plot(phlx, title="PHLX", type='candle', mav=(5, 10, 20, 60), style=style,
             savefig=r"/home/wtf81905/phlx.png")

    dow_path = r"/home/wtf81905/dow.png"
    nas_path = r"/home/wtf81905/nas.png"
    phlx_path = r"/home/wtf81905/phlx.png"

    time.sleep(5)  # 緩衝一下

    # 不開盤時傳送另一種訊息
    yesterday = dt.date.today() - dt.timedelta(days=1)  # 對我們來說是昨天
    open_result = []
    for d in dow[-1:].index:
        d = dt.datetime.date(d)
        open_result.append(d == yesterday)

    if False in open_result:
        context.bot.send_message(chat_id="your id",
                                 text=
                                 f"早安，您好！今天是{dt.date.today()}\n"
                                 "昨天美股沒有開盤!")
    else:
        # 道瓊
        context.bot.send_message(chat_id="your id",
                                 text=
                                 f"早安，您好！今天是{dt.date.today()}\n"
                                 "道瓊指數的部分\n"
                                 f"昨天收在 {round(dow_today[0], 2)}，相較前一天 {up_dow[0]}{abs(up_dow[1])} 點\n"
                                 f"目前站上均線: {a.join(dow_ma.get('站上'))}\n"
                                 f"目前跌破均線: {a.join(dow_ma.get('跌破'))}\n"
                                 f"目前貼齊的均線: {a.join(dow_ma.get('貼齊'))}\n"
                                 f"近期的最高點在 {high_dow[0]}\n"
                                 f"高點為 {round(high_dow[1], 2)}\n"
                                 f"與今天還相差 {round(high_dow[1] - dow_today[0], 2)} 點\n")
        context.bot.send_photo(chat_id="your id", photo=open(dow_path, "rb"))

        # 那斯達克
        context.bot.send_message(chat_id="your id", text="那斯達克的部分\n"
                                 f"昨天收在 {round(nas_today[0], 2)}，相較前一天 {up_nas[0]}{up_nas[1]} 點\n"
                                 f"目前站上均線: {a.join(nas_ma.get('站上'))}\n"
                                 f"目前跌破均線: {a.join(nas_ma.get('跌破'))}\n"
                                 f"目前貼齊的均線: {a.join(nas_ma.get('貼齊'))}\n"
                                 f"近期的最高點在 {high_nas[0]}\n"
                                 f"高點為 {round(high_nas[1], 2)}\n"
                                 f"與今天還相差 {round(high_nas[1] - nas_today[0], 2)} 點\n")
        context.bot.send_photo(chat_id="your id", photo=open(nas_path, "rb"))

        # 費城半導體
        context.bot.send_message(chat_id="your id", text=
                                 "最後看看費城半導體\n"
                                 f"昨天收在 {round(phlx_today[0], 2)}， 相較前一天 {up_phlx[0]}{abs(up_phlx[1])} 點\n"
                                 f"目前站上均線: {a.join(phlx_ma.get('站上'))}\n"
                                 f"目前跌破均線: {a.join(phlx_ma.get('跌破'))}\n"
                                 f"目前貼齊的均線: {a.join(nas_ma.get('貼齊'))}\n"
                                 f"近期的最高點在 {high_phlx[0]}\n"
                                 f"高點為 {round(high_phlx[1], 2)}\n"
                                 f"與今天還相差 {round(high_phlx[1] - phlx_today[0], 2)} 點\n")
        context.bot.send_photo(chat_id="your id", photo=open(phlx_path, "rb"))

        time.sleep(5)  # 緩衝一下

        # 發送總結
        context.bot.send_message(chat_id="your id", text=
                                 "總結一下各指數的狀況\n"
                                 f"道瓊指數目前 {situation_dow[0]}\n"
                                 f"{situation_dow[1]}"
                                 f"{judge_dow[0]}\n"
                                 "\n"
                                 f"那斯達克目前 {situation_nas[0]}\n"
                                 f"{situation_nas[1]}"
                                 f"{judge_nas[0]}\n"
                                 "\n"
                                 f"最後，費城半導體目前 {situation_phlx[0]}\n"
                                 f"{situation_phlx[1]}"
                                 f"{judge_phlx[0]}\n"
                                 "\n")


    # return dow_today, nas_today, phlx_today,\
    #        up_dow, up_nas, up_phlx, \
    #        dow_ma, nas_ma, phlx_ma, \
    #        high_dow, high_nas, high_phlx,\
    #        situation_dow, situation_nas, situation_phlx,\
    #        judge_dow, judge_nas, judge_phlx


def news(update, context):
    # 網址以及憑證
    ssl._create_default_https_context = ssl._create_unverified_context
    url = "https://news.cnyes.com/news/cat/us_stock"

    # 這邊建立一個物件，附加Request Headers資訊
    user = req.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36"})
    with req.urlopen(user) as r:
        data = r.read().decode("utf-8")

    # 這邊只取得我們想要的新聞資料
    now = dt.datetime.today()
    now = dt.datetime.date(now)
    yesterday = now - dt.timedelta(days=1)  # 對我們來說是昨天
    yesterday = dt.datetime.strftime(yesterday, "%Y-%m-%d")

    soup = BeautifulSoup(data, 'html.parser')
    news_result = soup.find_all("a", class_="_1Zdp")

    count = 0
    for n in news_result:
        need = n.select_one("time")
        need = need["datetime"][0:10]
        if yesterday == need:
            count += 1  # 這邊可以只擷取當天的，但這樣會變成說，在下午或晚上使用的時候會有時差，造成沒有最新的資料
    all_news = []
    for u in news_result[0: count + 1]:
        all_news.append(u["title"])
        all_news.append(r"https://news.cnyes.com" + u["href"] + "\n")
    b = ""
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=f"您好，為您提供最新的新聞資訊: \n{b.join(all_news)}")


execution_time_download_and_send = dt.time(7, 30, 00, 000000, tzinfo=taiwan)  # 定時下載及發送訊息
# 每個星期2 ~ 6定時下載以及發送訊息
job_rue_download = job.run_daily(callback=auto_download_and_send,
                                 time=execution_time_download_and_send,
                                 days=(1, 2, 3, 4, 5))

start_handler = CommandHandler("start", start)  # 指令: /start，傳送 def start 內部設定的訊息
news_handler = CommandHandler("news", news)
dispatcher.add_handler(start_handler)  # 包裝
dispatcher.add_handler(news_handler)  # 包裝
updater.start_polling()  # 開始
updater.idle()
