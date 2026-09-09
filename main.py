import os
import json
import html
import asyncio
import logging
import re

import requests
import feedparser

from telegram import Bot, InputMediaPhoto
from telegram.constants import ParseMode


# ============================================================
# 文件路径
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

CONFIG_FILE = os.path.join(
    BASE_DIR,
    "config.json"
)

SENT_FILE = os.path.join(
    BASE_DIR,
    "sent.json"
)


# ============================================================
# Nitter 实例
# ============================================================

NITTER_INSTANCES = [

    "https://nitter.cf",

]


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
# 读取配置
# ============================================================

def load_config():

    if not os.path.exists(
        CONFIG_FILE
    ):

        logger.error(
            "找不到 config.json"
        )

        raise FileNotFoundError(
            CONFIG_FILE
        )


    with open(
        CONFIG_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# ============================================================
# 已发送记录
# ============================================================

def load_sent():

    if not os.path.exists(
        SENT_FILE
    ):

        return {}


    try:

        with open(
            SENT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)


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


    # br 转换换行

    text = re.sub(

        r"<br\s*/?>",

        "\n",

        text,

        flags=re.I

    )


    # p 转换换行

    text = re.sub(

        r"</p>",

        "\n",

        text,

        flags=re.I

    )


    # 删除 HTML 标签

    text = re.sub(

        r"<[^>]+>",

        "",

        text

    )


    return html.unescape(
        text
    ).strip()


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


        media_type = enclosure.get(

            "type",

            ""

        )


        if (

            url

            and

            (

                "image" in media_type

                or

                media_type == ""

            )

        ):

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

        if url.startswith(
            "/"
        ):

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

    return list(

        dict.fromkeys(
            images
        )

    )


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


    match = re.search(

        r"(\d{10,})",

        str(entry_id)

    )


    if match:

        return match.group(1)


    # 最后备用

    return str(
        entry_id or link
    )


# ============================================================
# 获取 Nitter RSS
# ============================================================

def get_tweets(username):

    for instance in NITTER_INSTANCES:

        url = (
            f"{instance}/"
            f"{username}/rss"
        )


        try:

            logger.info(
                f"[Nitter] 获取：{url}"
            )


            response = session.get(

                url,

                timeout=30

            )


            logger.info(

                f"[Nitter] HTTP "
                f"{response.status_code}"

            )


            if response.status_code != 200:

                continue


            content_type = response.headers.get(

                "Content-Type",

                ""

            )


            logger.info(

                f"[Nitter] Content-Type: "
                f"{content_type}"

            )


            feed = feedparser.parse(

                response.content

            )


            # 检查 RSS 是否有错误

            if feed.bozo:

                logger.warning(

                    "[Nitter] RSS解析警告："

                    f"{feed.bozo_exception}"

                )


            if not feed.entries:

                logger.warning(
                    "[Nitter] RSS 没有推文"
                )

                logger.warning(

                    "[Nitter] 返回内容前200字符："

                    f"{response.text[:200]}"

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


                    # Nitter 链接改成 X 链接

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

                        "images": images

                    })


                except Exception as e:

                    logger.warning(

                        "[Nitter] "
                        f"解析推文失败：{e}"

                    )


            if tweets:

                logger.info(

                    "[Nitter] "
                    f"成功获取 "
                    f"{len(tweets)} 条推文"

                )

                return tweets


        except Exception as e:

            logger.warning(

                "[Nitter] 请求失败："
                f"{e}"

            )


    logger.error(

        "[Nitter] 所有实例失败："
        f"@{username}"

    )

    return []


# ============================================================
# 构建 Telegram 消息
# ============================================================

def build_message(tweet):

    username = tweet[
        "username"
    ]


    text = tweet.get(
        "text",
        ""
    )


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

            f"{html.escape(text)}"

        )


    message += (

        "\n\n🔗 "

        f'<a href="{html.escape(url)}">'

        "查看原推文"

        "</a>"

    )


    # Telegram 最大 4096

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

    tweet,

    config

):

    message = build_message(
        tweet
    )


    images = tweet.get(

        "images",

        []

    )


    # --------------------------------------------------------
    # 图片
    # --------------------------------------------------------

    if (

        config.get(

            "send_images",

            True

        )

        and

        images

    ):

        try:

            # 单图

            if len(images) == 1:

                await bot.send_photo(

                    chat_id=chat_id,

                    photo=images[0],

                    caption=message,

                    parse_mode=ParseMode.HTML

                )


            # 多图

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

                f"图片发送成功："
                f"{tweet['id']}"

            )


            return True


        except Exception as e:

            logger.warning(

                f"图片发送失败：{e}"

            )

            logger.info(
                "改为文字发送"
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

        f"文字发送成功："
        f"{tweet['id']}"

    )


    return True


# ============================================================
# 检查用户
# ============================================================

async def check_user(

    bot,

    username,

    config,

    sent

):

    logger.info(
        "=" * 55
    )


    logger.info(
        f"检查 @{username}"
    )


    tweets = get_tweets(
        username
    )


    if not tweets:

        logger.warning(
            f"没有获取到 @{username} 的推文"
        )

        return


    # --------------------------------------------------------
    # RSS 最新通常在前
    #
    # Snowflake ID 排序更可靠
    # --------------------------------------------------------

    try:

        tweets.sort(

            key=lambda x: int(
                x["id"]
            )

        )


    except Exception:

        tweets.reverse()


    # --------------------------------------------------------
    # 第一次运行
    # --------------------------------------------------------

    if username not in sent:

        sent[username] = []


        # 默认不发送历史

        if not config.get(

            "send_startup_history",

            False

        ):

            for tweet in tweets:

                sent[username].append(

                    tweet["id"]

                )


            sent[username] = list(

                dict.fromkeys(

                    sent[username]

                )

            )[-500:]


            save_sent(
                sent
            )


            logger.info(

                "首次运行："

                f"已记录 {len(tweets)} 条历史推文"

            )


            return


    # --------------------------------------------------------
    # 已发送
    # --------------------------------------------------------

    old_ids = set(

        sent.get(

            username,

            []

        )

    )


    new_tweets = []


    for tweet in tweets:

        if tweet["id"] not in old_ids:

            new_tweets.append(
                tweet
            )


    # --------------------------------------------------------
    # 没有新推文
    # --------------------------------------------------------

    if not new_tweets:

        logger.info(
            "没有新推文"
        )

        return


    logger.info(

        f"发现 "
        f"{len(new_tweets)} 条新推文"

    )


    # --------------------------------------------------------
    # 发送
    # --------------------------------------------------------

    for tweet in new_tweets:

        try:

            success = await send_tweet(

                bot,

                config[
                    "telegram_chat_id"
                ],

                tweet,

                config

            )


            if success:

                sent.setdefault(

                    username,

                    []

                )


                sent[username].append(

                    tweet["id"]

                )


                # 保留最近500条

                sent[username] = list(

                    dict.fromkeys(

                        sent[username]

                    )

                )[-500:]


                save_sent(
                    sent
                )


            # 多条推文之间间隔 1 秒

            await asyncio.sleep(
                1
            )


        except Exception as e:

            logger.exception(

                f"发送失败：{e}"

            )


# ============================================================
# 主程序
# ============================================================

async def main():

    print()

    print(
        "=" * 65
    )

    print(
        "       X / Twitter → Telegram 自动同步器"
    )

    print(
        "       Nitter RSS 版本"
    )

    print(
        "       单次运行模式"
    )

    print(
        "=" * 65
    )

    print()


    # ========================================================
    # 读取配置
    # ========================================================

    config = load_config()


    bot_token = config.get(

        "telegram_bot_token",

        ""

    )


    if not bot_token:

        logger.error(
            "没有填写 Bot Token"
        )

        return


    users = config.get(

        "twitter_users",

        []

    )


    if not users:

        logger.error(
            "没有设置 Twitter 用户"
        )

        return


    # ========================================================
    # Telegram Bot
    # ========================================================

    bot = Bot(

        token=bot_token

    )


    try:

        me = await bot.get_me()


        logger.info(

            "Telegram Bot 已连接："

            f"@{me.username}"

        )


    except Exception as e:

        logger.error(

            f"Telegram 连接失败：{e}"

        )

        return


    # ========================================================
    # 已发送记录
    # ========================================================

    sent = load_sent()


    logger.info(

        f"监控用户：{users}"

    )


    # ========================================================
    # 单次执行
    # ========================================================

    try:

        for username in users:

            username = username.strip()

            username = username.lstrip("@")

            if not username:

                continue


            await check_user(

                bot,

                username,

                config,

                sent

            )


            # 多个用户之间间隔 2 秒

            await asyncio.sleep(
                2
            )


        logger.info(
            "=" * 55
        )

        logger.info(
            "本次检查完成，程序退出"
        )

        logger.info(
            "=" * 55
        )


    except Exception as e:

        logger.exception(

            f"本次检查发生错误：{e}"

        )


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print(
            "\n程序已退出"
        )