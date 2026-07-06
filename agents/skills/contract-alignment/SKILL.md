---
name: contract-alignment
version: "1.0"
trigger: pre_implementation
description: 实现前对照计划逐条校验实现方案的一致性，发现偏差立即回到规划而不是带着偏差实现
input: implementation approach + planning output (from context)
output: item-by-item alignment verdict against the plan
---

# Contract Alignment Skill

## Goal
在进入实现/验证之前，把实现方案与前面产出的计划（契约）逐条对照，确认没有偏离。带着偏差进入实现的成本远高于现在回到规划。

## Process
1. 取出计划中的每一个步骤/承诺（文件、接口、行为）
2. 对照当前的实现方案，逐条标注：一致 / 有偏差（说明偏差内容）
3. 对每个偏差判断：是实现方案错了，还是计划本身需要更新
4. 给出总体结论：一致可继续，或列出必须先解决的偏差

## Output Format
- **逐条对照**：计划条目 → 一致 / 偏差说明（引用具体文件或步骤编号）
- **总体结论**：一致 / 存在偏差需回到规划

## Quality Bar
每条结论必须引用计划中的具体条目（文件名或步骤号），不接受笼统的"整体一致"。
