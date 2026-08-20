# IPC 帧协议 v1

安装脚本创建 `C:\ProgramData\SSKJVirtualCamera\frames.v1.bin`。Python 与
Frame Server 分别把同一文件映射到内存；映射由一个 128 字节头部和两个等长
NV12 帧槽组成。使用文件映射是为了跨越桌面会话与 Frame Server Session 0。

## 发布顺序

1. 写入端选择 `(published_sequence + 1) % 2` 对应的非活动帧槽。
2. 完整复制 NV12 帧。
3. 更新 100 ns 单位的单调时钟时间戳。
4. 最后通过对齐的 64 位写操作发布新序号。

读取端先读取序号，复制对应帧槽，再次读取序号；两次序号不一致时丢弃副本并重试。
这避免锁住 Python 播放循环，也避免 Frame Server 读到半帧。

## ABI

头部使用小端、固定宽度整数，不包含指针或平台相关的 `size_t`。C++ 通过
`static_assert` 固定大小和对齐；Python 使用 `<8sHH9I3Q48s8x` 验证 128 字节布局。

不兼容修改必须增加主版本号并使用新的帧文件名；兼容扩展只能占用保留区，且
必须增加次版本号。
