"""UI translations for FH6Gacha."""

LANGUAGE_NAMES = {"zh": "中文", "en": "English"}

POLICY_LABELS = {
    "zh": {
        "threshold": "按价格判断（OCR 失败时保留）",
        "sell_all": "重复车辆全部出售",
        "keep_all": "重复车辆全部保留",
    },
    "en": {
        "threshold": "Use price threshold (keep on OCR failure)",
        "sell_all": "Sell every duplicate car",
        "keep_all": "Keep every duplicate car",
    },
}

TEXTS = {
    "zh": {
        "window_title": "FH6 抽奖助手 · 独立 / 联动",
        "brand_subtitle": "STEAM 后台抽奖与 FH6Auto 联动",
        "language": "语言",
        "status_ready": "待机",
        "status_standalone": "独立抽奖运行中",
        "status_bridge": "联动监听中",
        "status_stopping": "正在停止",
        "run_settings": "运行设置",
        "standalone_mode": "独立抽奖",
        "bridge_mode": "跟随 FH6Auto 自动循环",
        "normal_rounds": "普通抽奖次数",
        "super_rounds": "超级抽奖次数",
        "until_empty": "抽到耗尽",
        "duplicate_policy": "重复车策略",
        "price_threshold": "价格阈值",
        "phase_timeout": "阶段超时",
        "seconds": "秒",
        "fh6auto_dir": "FH6Auto 目录",
        "browse": "选择目录",
        "bridge_hint": "将启动官方 FH6Auto.exe；仍需在官方界面点击开始",
        "start": "开始运行  F8",
        "emergency_stop": "紧急停止",
        "hotkey_hint": "联动时 F8 同时停止两边；F9 由暂停/恢复握手专用",
        "stats_title": "本次累计",
        "stat_normal": "普通抽奖",
        "stat_super": "超级抽奖",
        "stat_duplicates": "重复车辆",
        "stat_kept": "保留车辆",
        "stat_sold": "出售车辆",
        "stat_sale_income": "重复车出售收入 CR",
        "stat_ocr_failed": "OCR 失败",
        "stat_bridge_cycles": "联动轮次",
        "income_note": (
            "收入只统计重复车辆出售所得；抽奖奖励中的 CR 暂不统计（没有可靠识别来源）"
        ),
        "log_title": "运行日志",
        "error_title": "无法开始",
        "at_least_one": "请至少配置一种抽奖次数，或勾选抽到耗尽",
        "invalid_bridge_dir": "所选目录必须同时包含 FH6Auto.exe 和 config.json",
        "close_running_auto": (
            "请先关闭正在运行的 FH6Auto；桥接器需要在启动前临时启用诊断日志"
        ),
        "route_error": "FH6Auto 联动要求 1→2→3→4→1 完整回环：\n{errors}",
        "standalone_done": "独立抽奖完成",
        "standalone_incomplete": "独立抽奖未安全完成",
        "standalone_error": "独立抽奖异常: {error}",
        "bridge_done": "联动任务完成",
        "bridge_incomplete": "联动任务已停止或需要人工检查",
        "bridge_error": "联动启动/运行失败: {error}",
        "close_auto_restore": "请关闭 FH6Auto；关闭后桥接器会恢复其关机/调试配置",
        "backup_retained": (
            "FH6Auto 仍在运行，已保留配置恢复备份；下次联动会继续使用原始值"
        ),
        "restore_failed": "恢复 FH6Auto 配置失败，已保留备份供下次恢复: {error}",
        "stop_requested": "收到紧急停止请求",
        "config_recovered": "已恢复上次异常退出遗留的 FH6Auto 配置",
    },
    "en": {
        "window_title": "FH6 Gacha · Standalone / FH6Auto Bridge",
        "brand_subtitle": "STEAM BACKGROUND WHEELSPINS + FH6AUTO BRIDGE",
        "language": "Language",
        "status_ready": "READY",
        "status_standalone": "STANDALONE RUNNING",
        "status_bridge": "BRIDGE LISTENING",
        "status_stopping": "STOPPING",
        "run_settings": "RUN SETTINGS",
        "standalone_mode": "Standalone wheelspins",
        "bridge_mode": "Follow FH6Auto loop",
        "normal_rounds": "Normal wheelspins",
        "super_rounds": "Super wheelspins",
        "until_empty": "Until exhausted",
        "duplicate_policy": "Duplicate-car policy",
        "price_threshold": "Price threshold",
        "phase_timeout": "Phase timeout",
        "seconds": "sec",
        "fh6auto_dir": "FH6Auto folder",
        "browse": "Browse",
        "bridge_hint": "Starts the official FH6Auto.exe; click Start in its own window",
        "start": "START  F8",
        "emergency_stop": "EMERGENCY STOP",
        "hotkey_hint": (
            "In bridge mode F8 stops both apps; F9 is reserved for pause/resume"
        ),
        "stats_title": "RUN TOTALS",
        "stat_normal": "Normal spins",
        "stat_super": "Super spins",
        "stat_duplicates": "Duplicate cars",
        "stat_kept": "Cars kept",
        "stat_sold": "Cars sold",
        "stat_sale_income": "Duplicate-car sale income (CR)",
        "stat_ocr_failed": "OCR failures",
        "stat_bridge_cycles": "Bridge cycles",
        "income_note": (
            "Income only includes duplicate-car sales. CR awarded by wheelspins is "
            "not counted because it has no reliable detection source."
        ),
        "log_title": "RUNTIME LOG",
        "error_title": "Unable to start",
        "at_least_one": (
            "Configure at least one wheelspin count or select Until exhausted."
        ),
        "invalid_bridge_dir": (
            "The selected folder must contain both FH6Auto.exe and config.json."
        ),
        "close_running_auto": (
            "Close the running FH6Auto first; the bridge must enable diagnostic "
            "logging before launch."
        ),
        "route_error": "FH6Auto bridge requires a complete 1→2→3→4→1 route:\n{errors}",
        "standalone_done": "Standalone wheelspins completed",
        "standalone_incomplete": "Standalone wheelspins did not finish safely",
        "standalone_error": "Standalone error: {error}",
        "bridge_done": "Bridge run completed",
        "bridge_incomplete": "Bridge stopped or requires manual inspection",
        "bridge_error": "Bridge launch/runtime error: {error}",
        "close_auto_restore": (
            "Close FH6Auto so its shutdown/debug settings can be restored."
        ),
        "backup_retained": (
            "FH6Auto is still running. The recovery backup was retained for the next "
            "bridge launch."
        ),
        "restore_failed": (
            "Could not restore FH6Auto settings; the recovery backup was retained: "
            "{error}"
        ),
        "stop_requested": "Emergency stop requested",
        "config_recovered": (
            "Recovered FH6Auto settings left by the previous abnormal exit"
        ),
    },
}


def tr(language, key, **values):
    language = language if language in TEXTS else "zh"
    return TEXTS[language][key].format(**values)
