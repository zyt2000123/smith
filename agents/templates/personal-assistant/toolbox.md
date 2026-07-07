# Personal Assistant Tools

## Local Context
- **read_file** — 阅读仓库、配置、日志、文档，先理解现状
- **write_file** — 生成或更新文件，沉淀结果
- **shell** — 运行命令、测试、脚本与最小验证

## External Context
- **web_search** — 搜索外部资料、产品信息、官方文档入口
- **web_fetch** — 抓取已确认 URL 的正文内容，做准确信息提取

## Workflow
- **skill_load** — 按任务类型加载合适技能，尤其是规划、调试、评审类技能
- **skill_manage** — 管理和演化可复用技能
- **memory_ops** — 记录用户偏好、任务状态、长期上下文
- **git_ops** — 查看状态、提交、推送、创建分支等 Git 操作

## Best Practices
- 先 `read_file` / `shell` 确认现状，再 `write_file`
- 先 `web_search` 再 `web_fetch`，避免盲抓网页
- 只在真正有价值时记录记忆，避免把瞬时噪音写进长期上下文
- Git 操作围绕当前任务最小化，避免把无关改动卷进来
