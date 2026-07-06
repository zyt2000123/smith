---
name: understand
version: "1.0"
trigger: task_start
description: 在动手前准确复述需求并识别边界条件，作为后续所有步骤的共同基准
input: raw task description
output: requirement restatement + boundary conditions + assumptions
---

# Understand Skill

## Goal
在做任何规划或实现之前，先证明自己真正理解了任务：用自己的话复述需求，并把边界条件、约束和假设显式列出来。

## Process
1. 用自己的话复述需求：用户到底想要什么？完成后的状态是什么样？
2. 列出边界条件：什么在范围内、什么不在范围内（不包括的事项要明说）
3. 列出约束与前提假设：技术约束、环境前提、依赖条件
4. 指出需求中模糊或有歧义的点（如果有）

## Output Format
- **需求复述**：一到两句话
- **边界条件**：至少 2 条（范围内 / 范围外）
- **约束与假设**：逐条列出
- **模糊点**：没有则写"无"

## Quality Bar
复述必须比原始描述更具体，不能是原文改写；边界条件必须是可判定的（能回答"这个算不算在内"）。
