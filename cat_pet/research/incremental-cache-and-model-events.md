# 增量缓存与后台模型研究

本轮已实现：按窗口、绑定 Session、已验证 UIA 会话身份隔离的运行内缓存（最多 8 个会话，每会话 1000 条）；主动补读从当前已加载底部开始，匹配至少两条唯一正文重叠后停止翻旧消息。无法确认衔接不修改缓存，提示重建历史基线。缓存不落盘、不跨进程恢复，不具备稳定业务消息 ID。

菜单增加补读新增消息、总结缓存/提取待办、清空缓存。摘要通过配置的大模型生成，引用本次缓存编号并附原文；生成期间仍校验绑定会话。未自动调用模型、未自动发送。后台未打开会话读取、自动新增提醒和跨启动断点恢复尚未实现。

静态元数据新增调查（已核对版本 Weixin 4.1.13.12）：

- RecyclerListView 元对象 0x8b56b28：OnDoHandleItem、DidReload、DidDiffUpdate、ContentScrolledBy、OverscrollChanged。
- 其父 VirtualScrollArea 元对象 0x8b56a10：ScrollingStarted、ScrollingEnded、VScrollBarSliderMoved。
- ChatSessionCell 元对象 0x8b36db8：contextMenuAboutToShow；父 XTableCell 0x8b57210：MenuForEvent。

这些是类级静态方法/信号声明，不证明后台会话模型存在，也不证明能够从外部直接订阅。当前没有执行内部函数或安装进程内信号适配；仍需确认模型所有权、会话标识映射、信号参数与生命周期。

摄像头监控增加 monitor_on_startup，默认 false。设置页“检测与触发”可更改，下次启动生效；快捷键和手动启用照常工作。
