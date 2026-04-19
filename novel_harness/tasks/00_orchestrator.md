# 任务：写作 Orchestrator

## 目的

根据用户给出的章节目标，选择合适任务链，协调规划、生成、检查、修订、连续性更新。

## 输入

- 用户目标：要写哪一卷、哪一章、什么场景或什么功能。
- 当前连续性账本：`context/04_continuity_ledger.md`
- 项目圣经：`../NOVEL_BLUEPRINT.md`
- 长期框架：`context/06_progressive_framework.md`
- 人物羁绊：`context/07_character_bonds.md`

## 推荐流程

1. 若用户只给模糊目标，先生成章节 brief。
2. 若缺章节结构，调用 `tasks/02_chapter_outline.md`。
3. 若已有章节结构，调用 `tasks/03_chapter_draft.md`。
4. 生成后用 `checks/01_quality_rubric.md`、`checks/02_continuity_check.md`、`checks/03_style_check.md` 检查。
5. 若涉及管理升级、衡山、学派或诸子百家，还必须用 `checks/04_plot_logic_check.md` 检查认知阶梯和因果链。
6. 若未通过，调用 `tasks/04_chapter_rewrite.md`。
7. 最终调用 `tasks/05_continuity_update.md` 更新账本。

## 输出

给用户：

- 本次采用的任务链。
- 生成或修改的文件。
- 下一步建议。
