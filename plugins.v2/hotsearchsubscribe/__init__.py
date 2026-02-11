import datetime
import json
from threading import Event
from typing import Tuple, List, Dict, Any, Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.chain.subscribe import SubscribeChain
from app.core.config import settings
from app.core.context import MediaInfo
from app.core.metainfo import MetaInfo
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import MediaType
from app.utils.http import RequestUtils

from app.modules.themoviedb.tmdbapi import TmdbApi


class HotSearchSubscribe(_PluginBase):
    """
    热搜关键词订阅插件
    从指定URL获取热搜关键词并自动添加到订阅
    """

    # 插件名称
    plugin_name = "HH热搜关键词订阅"
    # 插件描述
    plugin_desc = "获取HH热搜关键词，自动添加到订阅。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/Exlany/MoviePilot-Plugins/main/icons/hotsearch.png"
    # 插件版本
    plugin_version = "1.3"
    # 插件作者
    plugin_author = "Lany"
    # 作者主页
    author_url = "https://github.com/Exlany"
    # 插件配置项ID前缀
    plugin_config_prefix = "hotsearch_"
    # 加载顺序
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 1

    # 退出事件
    _event = Event()
    # 私有属性
    subscribechain: SubscribeChain = None
    _scheduler = None
    _enabled = False
    _onlyonce = False
    _cron = ""
    _clear = False
    _url = "https://hhanclub.net/suggest.php?hot_search=1"
    _num = 1
    _media_type = "all"

    # TmdbApi 实例
    tmdbapi: Optional[TmdbApi] = None

    # 内置数据源选项
    DATA_SOURCES = [
        {"title": "憨憨", "value": "https://hhanclub.net/suggest.php?hot_search=1"}
    ]

    def init_plugin(self, config: dict = None):
        self.subscribechain = SubscribeChain()

        # 初始化 tmdbapi，使用 moviepilot 已封装的接口
        try:
            self.tmdbapi = TmdbApi()
        except Exception as e:
            logger.error(f"初始化 TmdbApi 失败: {e}")
            self.tmdbapi = None

        if config:
            self._enabled = config.get("enabled", False)
            self._cron = config.get("cron", "")
            self._clear = config.get("clear", False)
            self._onlyonce = config.get("onlyonce", False)
            self._url = config.get("url", self.DATA_SOURCES[0]["value"])
            self._num = config.get("num", 1)
            self._media_type = config.get("media_type", "all")

        # 停止现有任务
        self.stop_service()

        # 启动服务
        # 清理插件历史
        if self._clear:
            self.del_data(key="history")
            self._clear = False
            self.__update_config()
            logger.info("历史清理完成")

        if self._enabled or self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            # 周期执行
            if self._cron:
                logger.info(f"热搜关键词订阅服务启动，周期：{self._cron}")
                try:
                    self._scheduler.add_job(
                        func=self.__refresh_hot_search,
                        trigger=CronTrigger.from_crontab(self._cron),
                        name="热搜关键词订阅",
                    )
                except Exception as e:
                    logger.error(f"热搜关键词订阅服务启动失败，错误信息：{str(e)}")
                    self.systemmessage.put(
                        f"热搜关键词订阅服务启动失败，错误信息：{str(e)}"
                    )
            else:
                self._scheduler.add_job(
                    func=self.__refresh_hot_search,
                    trigger=CronTrigger.from_crontab("0 9 * * *"),
                    name="热搜关键词订阅",
                )
                logger.info("热搜关键词订阅服务启动，周期：每天 09:00")

            # 一次性执行
            if self._onlyonce:
                logger.info("热搜关键词订阅服务启动，立即运行一次")
                self._scheduler.add_job(
                    func=self.__refresh_hot_search,
                    trigger="date",
                    run_date=datetime.datetime.now(tz=pytz.timezone(settings.TZ))
                    + datetime.timedelta(seconds=3),
                )
                # 关闭一次性开关
                self._onlyonce = False
                # 保存配置
                self.__update_config()

            if self._scheduler.get_jobs():
                # 启动服务
                self._scheduler.print_jobs()
                self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "onlyonce",
                                            "label": "立即运行一次",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VCronField",
                                        "props": {
                                            "model": "cron",
                                            "label": "执行周期",
                                            "placeholder": "5位cron表达式，留空自动",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "clear",
                                            "label": "清理历史记录",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 12},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "url",
                                            "label": "数据源",
                                            "items": self.DATA_SOURCES,
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "multiple": False,
                                            "chips": True,
                                            "model": "num",
                                            "label": "订阅关键词数量",
                                            "items": [
                                                {"title": "1", "value": 1},
                                                {"title": "2", "value": 2},
                                                {"title": "3", "value": 3},
                                                {"title": "5", "value": 5},
                                                {"title": "10", "value": 10},
                                            ],
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "media_type",
                                            "label": "媒体类型",
                                            "items": [
                                                {"title": "全部", "value": "all"},
                                                {"title": "电影", "value": "movie"},
                                                {"title": "电视剧", "value": "tv"},
                                            ],
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "cron": "",
            "clear": False,
            "url": self.DATA_SOURCES[0]["value"],
            "num": 1,
            "media_type": "all",
        }

    def get_page(self) -> List[dict]:
        """
        拼装插件详情页面，需要返回页面配置，同时附带数据
        """
        # 查询历史记录
        historys = self.get_data("history")
        if not historys:
            return [
                {
                    "component": "div",
                    "text": "暂无数据",
                    "props": {
                        "class": "text-center",
                    },
                }
            ]
        # 数据按时间降序排序
        historys = sorted(historys, key=lambda x: x.get("time"), reverse=True)
        # 拼装页面
        contents = []
        for history in historys:
            title = history.get("title")
            poster = history.get("poster")
            mtype = history.get("type")
            time_str = history.get("time")
            tmdb_id = history.get("tmdbid")
            season = history.get("season")
            if mtype == MediaType.TV.value:
                href = f"https://www.themoviedb.org/tv/{tmdb_id}"
            else:
                href = f"https://www.themoviedb.org/movie/{tmdb_id}"

            # 构建详情文本列表
            detail_items = [
                {
                    "component": "VCardText",
                    "props": {"class": "pa-0 px-2"},
                    "text": f"类型：{mtype}",
                },
            ]
            # 电视剧显示季号，电影不显示
            if mtype == MediaType.TV.value:
                detail_items.append(
                    {
                        "component": "VCardText",
                        "props": {"class": "pa-0 px-2"},
                        "text": f"第 {season} 季" if season else "季数：全部",
                    }
                )
            detail_items.append(
                {
                    "component": "VCardText",
                    "props": {"class": "pa-0 px-2"},
                    "text": f"订阅时间：{time_str}",
                }
            )
            contents.append(
                {
                    "component": "VCard",
                    "content": [
                        {
                            "component": "div",
                            "props": {
                                "class": "d-flex justify-space-start flex-nowrap flex-row",
                            },
                            "content": [
                                {
                                    "component": "div",
                                    "content": [
                                        {
                                            "component": "VImg",
                                            "props": {
                                                "src": poster,
                                                "height": 120,
                                                "width": 80,
                                                "aspect-ratio": "2/3",
                                                "class": "object-cover shadow ring-gray-500",
                                                "cover": True,
                                            },
                                        }
                                    ],
                                },
                                {
                                    "component": "div",
                                    "content": [
                                        {
                                            "component": "VCardSubtitle",
                                            "props": {
                                                "class": "pa-2 font-bold break-words whitespace-break-spaces"
                                            },
                                            "content": [
                                                {
                                                    "component": "a",
                                                    "props": {
                                                        "href": href,
                                                        "target": "_blank",
                                                    },
                                                    "text": title,
                                                }
                                            ],
                                        },
                                        *detail_items,
                                    ],
                                },
                            ],
                        }
                    ],
                }
            )

        return [
            {
                "component": "div",
                "props": {
                    "class": "grid gap-3 grid-info-card",
                },
                "content": contents,
            }
        ]

    def stop_service(self):
        """
        停止服务
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._event.set()
                    self._scheduler.shutdown()
                    self._event.clear()
                self._scheduler = None
        except Exception as e:
            logger.error(f"停止服务失败: {e}")

    def __update_config(self):
        """
        更新配置
        """
        self.update_config(
            {
                "enabled": self._enabled,
                "cron": self._cron,
                "clear": self._clear,
                "onlyonce": self._onlyonce,
                "url": self._url,
                "num": self._num,
                "media_type": self._media_type,
            }
        )

    def __refresh_hot_search(self):
        """
        刷新热搜关键词数据
        """
        logger.info(f"开始刷新热搜关键词订阅...")
        history: List[dict] = self.get_data("history") or []

        # 获取热搜关键词
        keywords = self.__get_hot_search()
        if not keywords:
            logger.warn("未获取到热搜关键词")
            return

        # 添加订阅
        self.__add_subscribe(keywords, history)

        # 保存历史记录
        self.save_data("history", history)
        logger.info(f"热搜关键词订阅刷新完成")

    def __get_hot_search(self) -> List[str]:
        """
        从指定URL获取热搜关键词
        """
        try:
            # 发送HTTP请求
            res = RequestUtils().get_res(self._url)
            if not res or not res.content:
                logger.error(f"获取热搜关键词失败，URL: {self._url}")
                return []

            # 尝试直接解析JSON
            try:
                data = res.json()
            except Exception:
                try:
                    data = json.loads(res.content.decode("utf-8"))
                except Exception as e:
                    logger.error(f"解析JSON失败: {str(e)}")
                    return []

            if not data:
                logger.error(f"解析热搜关键词失败，返回数据为空")
                return []

            # 提取关键词
            keywords = []
            for item in data[: self._num]:
                keyword = item.get("keywords")
                if keyword:
                    # 处理Unicode转义序列
                    if "\\u" in keyword:
                        try:
                            keyword = keyword.encode("utf-8").decode("unicode_escape")
                        except Exception:
                            pass
                    keywords.append(keyword)

            logger.info(f"获取到热搜关键词: {keywords}")
            return keywords
        except Exception as e:
            logger.error(f"获取热搜关键词异常: {str(e)}")
            return []

    def __add_subscribe(self, keywords: List[str], history: List[dict]):
        """
        添加订阅
        """
        for keyword in keywords:
            try:
                # 检查是否已处理过
                unique_flag = f"hotsearch: {keyword}"
                if any(h.get("unique") == unique_flag for h in history):
                    logger.info(f"关键词已存在订阅: {keyword}")
                    continue

                # 元数据
                meta = MetaInfo(keyword)
                # 匹配媒体信息
                mediainfo: MediaInfo = self.chain.recognize_media(
                    meta=meta, cache=False
                )
                if not mediainfo:
                    logger.warn(f"未识别到媒体信息，关键词：{keyword}")
                    continue

                # 媒体类型过滤
                if self._media_type == "movie" and mediainfo.type != MediaType.MOVIE:
                    logger.info(f"跳过非电影: {mediainfo.title}")
                    continue
                if self._media_type == "tv" and mediainfo.type != MediaType.TV:
                    logger.info(f"跳过非电视剧: {mediainfo.title}")
                    continue

                # 判断用户是否已经添加订阅
                if self.subscribechain.exists(mediainfo=mediainfo, meta=meta):
                    logger.info(f"{mediainfo.title_year} 订阅已存在")
                    continue

                # 获取电视剧最新季号
                season_to_subscribe = self.__get_latest_season(mediainfo, meta)

                # 添加订阅
                try:
                    self.subscribechain.add(
                        title=mediainfo.title,
                        year=mediainfo.year,
                        mtype=mediainfo.type,
                        tmdbid=mediainfo.tmdb_id,
                        season=season_to_subscribe or meta.end_season,
                        exist_ok=True,
                        username="热搜关键词订阅",
                    )
                except Exception as e:
                    logger.error(f"调用 subscribechain.add 失败: {e}")
                    raise

                # 存储历史记录
                history.append(
                    {
                        "title": mediainfo.title,
                        "type": mediainfo.type.value,
                        "year": mediainfo.year,
                        "poster": mediainfo.get_poster_image(),
                        "overview": mediainfo.overview,
                        "tmdbid": mediainfo.tmdb_id,
                        "season": season_to_subscribe,
                        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "unique": unique_flag,
                    }
                )
                logger.info(
                    f"添加订阅成功: {mediainfo.title} ({mediainfo.year})"
                    + (f" - 第 {season_to_subscribe} 季" if season_to_subscribe else "")
                )
            except Exception as e:
                logger.error(f"添加订阅失败: {keyword}, 错误: {str(e)}")

    def __get_latest_season(self, mediainfo: MediaInfo, meta: MetaInfo) -> Optional[int]:
        """
        获取电视剧最新季号
        """
        if mediainfo.type != MediaType.TV:
            return None

        # 优先使用已识别的季号
        if meta.end_season:
            return meta.end_season

        if not self.tmdbapi:
            return None

        # 尝试通过 tmdb_id 获取
        tmdb_id = getattr(mediainfo, "tmdb_id", None)
        if not tmdb_id:
            try:
                tmdb_match = self.tmdbapi.match(
                    name=mediainfo.title,
                    mtype=MediaType.TV,
                    year=mediainfo.year,
                )
                tmdb_id = tmdb_match.get("id") if tmdb_match else None
            except Exception as e:
                logger.debug(f"TmdbApi.match 获取 tmdb_id 失败: {e}")

        if not tmdb_id:
            return None

        try:
            tmdb_info = self.tmdbapi.get_info(mtype=MediaType.TV, tmdbid=tmdb_id)
            seasons = tmdb_info.get("seasons") or []
            season_nums = [
                s.get("season_number")
                for s in seasons
                if s.get("season_number") and s.get("season_number") > 0
            ]
            if season_nums:
                latest = max(season_nums)
                logger.info(f"获取到最新季：第 {latest} 季 - {mediainfo.title}")
                return latest
        except Exception as e:
            logger.debug(f"获取季信息失败: {e}")

        return None
