---
name: project-analysis
version: "1.0.0"
trigger: on_first_encounter
description: 自动分析项目结构，生成项目理解文档
input: project directory path
output: structured project profile saved to memory/project/
---

# Project Analysis Skill

## Goal
Agent 首次接触项目时，自动完成结构化分析，生成可复用的项目理解文档。
后续对话可直接引用分析结果，无需重复探索。

## Constraints
- 最大执行时间：5 分钟
- 最大文件读取次数：20 次
- 优先使用 `find` + `head` 快速扫描，避免读取完整文件
- 不修改项目中的任何文件

## Analysis Steps

### 1. 仓库发现
收集版本控制基本信息：
```
git remote -v
git branch -a
git log --oneline -10
```
记录：远程地址、默认分支、最近活跃度。

### 2. 技术栈识别
按优先级检测项目描述文件：
- `package.json` → Node.js / 前端
- `pyproject.toml` / `setup.py` / `requirements.txt` → Python
- `Cargo.toml` → Rust
- `go.mod` → Go
- `Package.swift` → Swift
- `pom.xml` / `build.gradle` → Java / Kotlin
- `Gemfile` → Ruby
- `composer.json` → PHP

对每个检测到的文件，用 `head -30` 提取名称、版本、主要依赖。

### 3. 目录结构扫描
```
find . -maxdepth 3 -type d | head -80
```
识别关键目录类型：
- **源码**: src/, lib/, app/, cmd/
- **测试**: test/, tests/, __tests__/, spec/
- **文档**: docs/, doc/, README*
- **配置**: .github/, .vscode/, docker/, k8s/
- **构建产物**: dist/, build/, target/, out/

### 4. 入口点定位
搜索常见入口模式：
- `main.py`, `main.go`, `main.rs`, `index.ts`, `App.swift`
- `Makefile`, `Dockerfile`, `docker-compose.yml`
- npm scripts (`package.json` 中的 `scripts` 字段)
- `pyproject.toml` 中的 `[project.scripts]`

对每个入口文件用 `head -20` 提取关键信息。

### 5. 依赖图谱
从步骤 2 检测到的描述文件中提取依赖列表，分类记录：
- **框架**: web 框架、UI 框架、测试框架
- **基础设施**: 数据库驱动、消息队列、缓存
- **工具链**: 构建工具、代码检查、格式化
- **业务**: 领域特定的库

### 6. 架构模式识别
根据目录结构和依赖推断：

| 信号 | 模式 |
|---|---|
| 多个独立 package.json / go.mod | Monorepo |
| 多个 Dockerfile + docker-compose | 微服务 |
| 单一入口 + 分层目录 | 单体 |
| routes/ + controllers/ + models/ | MVC |
| domain/ + application/ + infrastructure/ | DDD / 六边形架构 |
| handlers/ + services/ + repositories/ | 分层服务架构 |

API 风格检测：REST (router 文件)、GraphQL (schema 文件)、gRPC (proto 文件)。

## Output Format

将分析结果写入 `memory/project/profile.md`：

```markdown
# Project Profile

## Overview
- **Name**: [项目名]
- **Repository**: [remote URL]
- **Primary Language**: [语言]
- **Framework**: [主框架]
- **Architecture**: [模式]

## Tech Stack
| Category | Items |
|---|---|
| Language | ... |
| Framework | ... |
| Database | ... |
| Build Tool | ... |

## Directory Structure
[关键目录的树形表示，标注用途]

## Entry Points
| File | Purpose |
|---|---|
| ... | ... |

## Key Dependencies
[分类列表，附简要说明]

## Architecture Notes
[架构模式描述、分层关系、API 风格]
```
