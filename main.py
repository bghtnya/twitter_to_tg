import os
import json
import html
import logging
import re

import requests
import feedparser

from telegram import Bot, InputMediaPhoto
from telegram.constants import ParseMode


# ============================================================
# 配置
# ============================================================

NITTER_INSTANCES = [
    "https://nitter.cf",
]

TWITTER_USERS = [
    "bghtnya",
]

# True = 第一次运行时也发送 RSS 中已有的推文
# 建议第一次测试时改成 False
SEND_STARTUP_HISTORY = False

SEND_IMAGES = True

# 最多保存多少条 Tweet ID
MAX_SENT_IDS = 500

# Nitter 请求超时时间
REQUEST_TIMEOUT = 30


# ============================================================
# 文件
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

SENT_FILE = os.path.join(
    BASE_DIR,
    "sent.json"
)


# ============================================================
# 日志
# ============================================================

logging.basicConfig(

    level=logging.INFO,

    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),

    datefmt="%Y-%m-%d %H:%M:%S"

)

logger = logging.getLogger(
    "TwitterToTelegram"
)


# ============================================================
# HTTP Session
# ============================================================

session = requests.Session()

session.headers.update({

    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0.0.0 "
        "Safari/537.36"
    ),

    "Accept": (
        "application/rss+xml,"
        "application/xml,"
        "text/xml,"
        "*/*"
    ),

    "Accept-Language":
        "zh-CN,zh;q=0.9,en;q=0.8"

})


# ============================================================
# sent.json
# ============================================================

def load_sent():

    if not os.path.exists(SENT_FILE):

        return {}


    try:

        with open(
            SENT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)


        if not isinstance(data, dict):

            return {}


        return data


    except Exception as e:

        logger.warning(
            f"读取 sent.json 失败：{e}"
        )

        return {}


def save_sent(data):

    with open(
        SENT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(

            data,

            f,

            ensure_ascii=False,

            indent=2

        )


# ============================================================
# 清理 HTML
# ============================================================

def clean_html(text):

    if not text:

        return ""


    text = re.sub(

        r"<br\s*/?>",

        "\n",

        text,

        flags=re.I

    )


    text = re.sub(

        r"</p>",

        "\n",

        text,

        flags=re.I

    )


    text = re.sub(

        r"<[^>]+>",

        "",

        text

    )


    text = html.unescape(
        text
    )


    return text.strip()


# ============================================================
# 获取图片
# ============================================================

def extract_images(entry):

    images = []


    # --------------------------------------------------------
    # media_content
    # --------------------------------------------------------

    for media in entry.get(

        "media_content",

        []

    ):

        url = media.get(
            "url"
        )


        if url:

            images.append(
                url
            )


    # --------------------------------------------------------
    # enclosures
    # --------------------------------------------------------

    for enclosure in entry.get(

        "enclosures",

        []

    ):

        url = enclosure.get(
            "href"
        )


        if url:

            images.append(
                url
            )


    # --------------------------------------------------------
    # summary HTML
    # --------------------------------------------------------

    summary = entry.get(

        "summary",

        ""

    )


    image_urls = re.findall(

        r'<img[^>]+src=["\']([^"\']+)["\']',

        summary,

        re.I

    )


    for url in image_urls:

        if url.startswith("/"):

            url = (
                "https://nitter.cf"
                + url
            )


        images.append(
            url
        )


    # --------------------------------------------------------
    # 去重
    # --------------------------------------------------------

    result = []

    for url in images:

        if url not in result:

            result.append(url)


    return result


# ============================================================
# 获取 Tweet ID
# ============================================================

def get_tweet_id(entry):

    link = entry.get(
        "link",
        ""
    )


    match = re.search(

        r"/status/(\d+)",

        link

    )


    if match:

        return match.group(1)


    entry_id = entry.get(
        "id",
        ""
    )


    # RSS ID 里面寻找数字

    match = re.search(

        r"(\d{10,})",

        str(entry_id)

    )


    if match:

        return match.group(1)


    return str(
        entry_id or link
    )


# ============================================================
# 获取 Nitter RSS
# ============================================================

def fetch_tweets(username):

    for instance in NITTER_INSTANCES:

        url = (
            f"{instance}/"
            f"{username}/rss"
        )


        logger.info(
            f"[Nitter] 获取：{url}"
        )


        try:

            response = session.get(

                url,

                timeout=REQUEST_TIMEOUT

            )


            logger.info(

                f"[Nitter] HTTP "
                f"{response.status_code}"

            )


            if response.status_code != 200:

                logger.warning(

                    f"[Nitter] HTTP "
                    f"{response.status_code}"

                )

                continue


            feed = feedparser.parse(

                response.content

            )


            if feed.bozo:

                logger.warning(

                    "[Nitter] RSS解析警告："
                    f"{feed.bozo_exception}"

                )


            if not feed.entries:

                logger.warning(
                    "[Nitter] RSS 没有推文"
                )

                continue


            tweets = []


            for entry in feed.entries:

                try:

                    tweet_id = get_tweet_id(
                        entry
                    )


                    if not tweet_id:

                        continue


                    text = clean_html(

                        entry.get(

                            "summary",

                            ""

                        )

                    )


                    if not text:

                        text = clean_html(

                            entry.get(

                                "title",

                                ""

                            )

                        )


                    link = entry.get(

                        "link",

                        ""

                    )


                    # ------------------------------------------------
                    # Nitter URL → X URL
                    # ------------------------------------------------

                    if link:

                        link = re.sub(

                            r"https?://[^/]+",

                            "https://x.com",

                            link

                        )


                    images = extract_images(
                        entry
                    )


                    tweets.append({

                        "id": str(tweet_id),

                        "username": username,

                        "text": text,

                        "url": link,

                        "images": images,

                        "published": entry.get(
                            "published",
                            ""
                        )

                    })


                except Exception as e:

                    logger.warning(

                        f"[Nitter] "
                        f"解析推文失败：{e}"

                    )


            if tweets:

                logger.info(

                    f"[Nitter] 成功获取 "
                    f"{len(tweets)} 条推文"

                )

                return tweets


        except Exception as e:

            logger.warning(

                f"[Nitter] 请求失败：{e}"

            )


    logger.error(

        f"[Nitter] 所有实例失败："
        f"@{username}"

    )

    return []


# ============================================================
# 按 Tweet ID 排序
# ============================================================

def sort_tweets(tweets):

    try:

        return sorted(

            tweets,

            key=lambda x: int(
                x["id"]
            )

        )

    except Exception:

        return tweets


# ============================================================
# 构造 Telegram 消息
# ============================================================

def build_message(tweet):

    username = tweet[
        "username"
    ]


    text = tweet.get(
        "text",
        ""
    ).strip()


    url = tweet.get(
        "url",
        ""
    )


    message = (

        f"🐦 <b>@{html.escape(username)}</b>"

    )


    if text:

        message += (

            "\n\n"

            + html.escape(
                text
            )

        )


    if url:

        message += (

            "\n\n🔗 "

            f'<a href="{html.escape(url)}">'

            "查看原推文"

            "</a>"

        )


    # Telegram message 限制

    if len(message) > 4000:

        safe_text = html.escape(
            text
        )[:3500]


        message = (

            f"🐦 <b>@{html.escape(username)}</b>"

            "\n\n"

            f"{safe_text}"

            "\n\n🔗 "

            f'<a href="{html.escape(url)}">'

            "查看原推文"

            "</a>"

        )


    return message


# ============================================================
# Telegram 发送
# ============================================================

async def send_tweet(

    bot,

    chat_id,

    tweet

):

    message = build_message(
        tweet
    )


    images = tweet.get(
        "images",
        []
    )


    if SEND_IMAGES and images:

        try:

            # ------------------------------------------------
            # 单张图片
            # ------------------------------------------------

            if len(images) == 1:

                await bot.send_photo(

                    chat_id=chat_id,

                    photo=images[0],

                    caption=message,

                    parse_mode=ParseMode.HTML

                )


            # ------------------------------------------------
            # 多张图片
            # ------------------------------------------------

            else:

                media_group = []


                for index, image_url in enumerate(

                    images[:10]

                ):

                    if index == 0:

                        media_group.append(

                            InputMediaPhoto(

                                media=image_url,

                                caption=message,

                                parse_mode=ParseMode.HTML

                            )

                        )

                    else:

                        media_group.append(

                            InputMediaPhoto(

                                media=image_url

                            )

                        )


                await bot.send_media_group(

                    chat_id=chat_id,

                    media=media_group

                )


            logger.info(

                f"图片推送成功："
                f"{tweet['id']}"

            )


            return True


        except Exception as e:

            logger.warning(

                f"图片发送失败：{e}"

            )

            logger.warning(
                "尝试发送纯文字"
            )


    # --------------------------------------------------------
    # 文字
    # --------------------------------------------------------

    await bot.send_message(

        chat_id=chat_id,

        text=message,

        parse_mode=ParseMode.HTML,

        disable_web_page_preview=False

    )


    logger.info(

        f"文字推送成功："
        f"{tweet['id']}"

    )


    return True


# ============================================================
# 检查用户
# ============================================================

async def process_user(

    bot,

    chat_id,

    username,

    sent

):

    logger.info(
        "=" * 60
    )

    logger.info(
        f"检查 @{username}"
    )


    tweets = fetch_tweets(
        username
    )


    if not tweets:

        logger.warning(

            f"@{username} "
            "没有获取到推文"

        )

        return


    tweets = sort_tweets(
        tweets
    )


    old_ids = set(

        sent.get(

            username,

            []

        )

    )


    # ========================================================
    # 第一次运行
    # ========================================================

    if username not in sent:

        sent[username] = []


        if not SEND_STARTUP_HISTORY:

            for tweet in tweets:

                sent[username].append(

                    tweet["id"]

                )


            sent[username] = list(

                dict.fromkeys(

                    sent[username]

                )

            )[-MAX_SENT_IDS:]


            save_sent(
                sent
            )


            logger.info(

                f"首次运行："
                f"已记录 {len(tweets)} 条历史推文"

            )

            logger.info(
                "本次不发送历史推文"
            )

            return


    # ========================================================
    # 找新推文
    # ========================================================

    new_tweets = []


    for tweet in tweets:

        tweet_id = tweet["id"]


        if tweet_id not in old_ids:

            new_tweets.append(
                tweet
            )


    if not new_tweets:

        logger.info(
            "没有新推文"
        )

        return


    logger.info(

        f"发现 {len(new_tweets)} "
        "条新推文"

    )


    # ========================================================
    # 发送
    # ========================================================

    for tweet in new_tweets:

        try:

            success = await send_tweet(

                bot,

                chat_id,

                tweet

            )


            if success:

                sent.setdefault(

                    username,

                    []

                )


                sent[username].append(

                    tweet["id"]

                )


                sent[username] = list(

                    dict.fromkeys(

                        sent[username]

                    )

                )[-MAX_SENT_IDS:]


                save_sent(
                    sent
                )


        except Exception as e:

            logger.exception(

                f"发送 Tweet "
                f"{tweet['id']} 失败：{e}"

            )


# ============================================================
# 主程序
# ============================================================

async def main():

    logger.info(
        "=" * 60
    )

    logger.info(
        "X / Twitter → Telegram"
    )

    logger.info(
        "GitHub Actions 版本"
    )

    logger.info(
        "=" * 60
    )


    # --------------------------------------------------------
    # GitHub Secrets
    # --------------------------------------------------------

    bot_token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )


    chat_id = os.getenv(
        "TELEGRAM_CHAT_ID"
    )


    if not bot_token:

        raise RuntimeError(

            "缺少 TELEGRAM_BOT_TOKEN"

        )


    if not chat_id:

        raise RuntimeError(

            "缺少 TELEGRAM_CHAT_ID"

        )


    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    bot = Bot(
        token=bot_token
    )


    try:

        me = await bot.get_me()


        logger.info(

            f"Telegram Bot 已连接："
            f"@{me.username}"

        )


    except Exception as e:

        logger.error(

            f"Telegram Bot 连接失败："
            f"{e}"

        )

        raise


    # --------------------------------------------------------
    # sent.json
    # --------------------------------------------------------

    sent = load_sent()


    # --------------------------------------------------------
    # 检查所有用户
    # --------------------------------------------------------

    for username in TWITTER_USERS:

        username = username.strip()
        username = username.lstrip("@")

        await process_user(

            bot,

            chat_id,

            username,

            sent

        )


    logger.info(
        "=" * 60
    )

    logger.info(
        "本次检查完成"
    )

    logger.info(
        "=" * 60
    )


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":

    import asyncio

    try:

        asyncio.run(
            main()
        )

    except Exception as e:

        logger.exception(
            f"程序失败：{e}"
        )

        raise