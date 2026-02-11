# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

MoviePilot 第三方插件仓库。插件运行在 [MoviePilot](https://github.com/jxxghp/MoviePilot) 主应用中，本仓库只包含插件源码和发布配置。

## 仓库结构

```
plugins.v2/{plugin_id_lowercase}/   # v2 插件源码（每个插件一个目录，入口 __init__.py）
package.v2.json                     # 插件元数据注册表（名称、版本、图标、作者等）
icons/                              # 插件图标资源
.github/workflows/release.yml      # 自动发布 workflow
```

## 发布流程

修改 `package.v2.json` 中对应插件的 `version` 并设置 `"release": true`，push 到 main 后 GitHub Actions 自动：
1. 对比上一版本 tag，检测插件目录是否有变更
2. 打包为 `{plugin_id_lowercase}_v{version}.zip`（排除 `__pycache__`）
3. 创建 Release，tag 格式 `{PluginId}_v{Version}`

## 插件开发规范

### 新建插件
1. 创建 `plugins.v2/{plugin_id_lowercase}/__init__.py`
2. 在 `package.v2.json` 中添加元数据条目
3. 类继承 `app.plugins._PluginBase`，实现生命周期方法

### 插件类必须实现的属性和方法

类属性：
- `plugin_name`, `plugin_desc`, `plugin_icon`, `plugin_version`, `plugin_author`
- `plugin_config_prefix`（配置键前缀，如 `"hotsearch_"`）
- `plugin_order`（加载顺序）, `auth_level`（用户权限等级）

生命周期方法：
- `init_plugin(config: dict)` — 初始化，读取配置、启动调度器
- `stop_service()` — 停止调度器和后台任务
- `get_state() -> bool` — 返回启用状态
- `get_form() -> Tuple[List[dict], Dict[str, Any]]` — 返回 Vuetify 表单组件定义 + 默认值
- `get_page() -> List[dict]` — 返回插件详情页 Vuetify 组件树

可选方法：`get_command()`, `get_api()`

### 常用 MoviePilot 内部模块

```python
from app.plugins import _PluginBase          # 插件基类
from app.chain.subscribe import SubscribeChain  # 订阅链
from app.core.config import settings           # 全局配置（含 TZ 时区等）
from app.core.context import MediaInfo         # 媒体信息
from app.core.metainfo import MetaInfo         # 元数据解析
from app.modules.themoviedb.tmdbapi import TmdbApi  # TMDB API
from app.schemas import MediaType              # 媒体类型枚举
from app.utils.http import RequestUtils        # HTTP 请求工具
from app.log import logger                     # 日志
```

### 定时任务

使用 `apscheduler.schedulers.background.BackgroundScheduler`，时区取 `settings.TZ`。Cron 表达式为标准 5 位格式。

### 数据持久化

基类提供 `get_data(key)` / `save_data(key, value)` / `del_data(key)` 和 `update_config(dict)` 用于配置和数据存储。

### UI 表单

`get_form()` 返回 Vuetify 3 组件树（dict 嵌套），常用组件：`VSwitch`, `VSelect`, `VCronField`, `VTextField`。

## 代码风格

- Python 3，类型注解
- 私有方法双下划线前缀（`__method_name`）
- 配置键 snake_case，类名 PascalCase
- 日志使用 `logger.info/warn/error/debug`
- 用户通知使用 `self.systemmessage.put()`
