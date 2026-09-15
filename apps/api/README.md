# ApplyPilot 本机 API

API 实现位于 `applypilot/api`，通过项目 CLI 启动：

```bash
uv run applypilot api serve
```

默认只监听 `127.0.0.1:8765`。浏览器插件会优先请求 `/v1/forms/plan`，服务不可用时自动回退本地映射规则。接口合约和隐私边界见 [字段匹配 API 设计](../../docs/superpowers/specs/2026-09-15-profile-mapping-api-design.md)。
