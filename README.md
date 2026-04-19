# GenderSelect / 性别选择进化模拟

GenderSelect is a Python simulation framework for exploring why a "male slightly stronger, female slightly weaker" pattern may emerge in human evolutionary contexts, and under what conditions this pattern does or does not appear.

GenderSelect 是一个 Python 演化模拟框架，用于探索智人演化中“雄性略强、雌性略弱”这一现象在何种生态与社会条件下会涌现、何种条件下不会涌现。

## Research Motivation / 研究动机

My original motivation is:

> The repository is python code for Gender Select Pattern research for why male is stronger than female; which lead by my thought: male is less significant than female in the revolution condition, which cause male need to do more jobs with huge risk like hunting. High revolution pressure lead high strength gen expression, which make male stronger.

This project extends that intuition into a testable simulation hypothesis:

- Reproductive asymmetry may make female survival more critical to population recovery.
- Under high ecological and inter-group pressure, high-risk tasks (for example hunting and combat exposure) may be disproportionately allocated to individuals with stronger effective performance.
- Over long time horizons, division of labor, mating preference, injury risk, and resource constraints may jointly shape sex-differentiated trait expression.

Important note:

- This repository is for computational hypothesis testing, not for value judgment.
- Results are model-dependent and should be interpreted with caution.

本项目将以上直觉转化为可检验假设，并强调：

- 生育成本不对称可能使雌性存活在种群恢复中更关键。
- 在高生态压力和高竞争压力下，高风险任务会更可能分配给高有效表现个体。
- 长期上，分工、择偶偏好、受伤风险与资源约束的联合作用，可能塑造性别差异化表现。
- 本项目用于计算实验与假设检验，不包含价值判断。

## Core Questions / 核心问题

- Can a "male slightly stronger" phenotype emerge without hard-coding that outcome?
- How do hunting risk, injury dynamics, fertility constraints, and resource scarcity interact?
- Is the observed pattern robust across different environments and competition intensities?
- Which traits are favored in mating, birth, and offspring survival stages?

## Model Highlights / 模型亮点

- **Ability-driven assignment / 能力驱动分工**: no fixed 3-group preset in behavior assignment.
- **Injury dynamics / 受伤机制**: injury, recovery, worsening, and efficiency loss.
- **Shared carrying capacity / 共享K值**: food/productivity-driven S-curve pressure.
- **Evolvable mate preference / 可遗传择偶偏好**: resource/strength/intelligence/communication preference ratios.
- **Sex-specific expression genes / 性别特异表达基因**: expression can diverge through inheritance and mutation.
- **Three-stage selection metrics / 三阶段选择统计**:
  - mating stage
  - conception/birth stage
  - offspring survival stage

## Runtime Modes / 运行模式

```bash
# 1) Run with finite months / 有限月数运行
python main.py --preset default --months 1200

# 1.1) Daily tick mode / 以天为tick运行
python main.py --preset default --months 12 --time-unit day

# 1.2) Parallel tribe-local phases / 按部落并行执行可并行阶段
python main.py --preset default --months 1200 --parallel --max-workers 4

# 2) Long-running interactive mode / 持续运行（直到 stop）
python main.py --months -1 --report-interval 12 --run-name exp_live_01

# 3) Resume from latest checkpoint / 从最新检查点继续
python main.py --checkpoint auto

# 4) List presets / 查看预设
python main.py --list-presets
```

In interactive mode, you can type commands:

- `help`, `status`, `report`, `stop`, `checkpoint`, `plots`
- `set <scope.attr> <value>` (for runtime parameter injection)
- Example: `set mortality.base_mortality 0.0015`

## Outputs / 输出

- Per-run directory: `output/<run_name>/`
- Monthly CSV: `output/<run_name>/monthly_stats.csv`
- Optional plots (if matplotlib installed)

Main tracked outputs include:

- population, birth/death rates (total + sex-specific)
- innate/phenotypic strength statistics (mean + median)
- strength expression coefficients
- mate preference ratios
- three-stage selection indicators

## Project Structure / 项目结构

```text
simulation/
  core/
    events.py        # Domain events emitted by systems
    time.py          # Monthly/daily StepContext
    execution.py     # Sequential/threaded tribe executor
    scheduler.py     # Day-based system scheduler skeleton
  container.py
  models.py
  mechanisms.py
  metrics.py          # Role exposure, rate, and selection metric builders
  simulator.py
  visualization.py
  config_registry.py
  csv_exporter.py
  reproduction.py     # Mate pool, mate selection, conception, pregnancy, inheritance

main.py
run.py
```

## Architecture Direction / 架构方向

The current engine now has a small core layer:

- `StepContext` makes each tick explicit: one month by default, or one day with `--time-unit day`.
- Per-tribe phases can run through `ParallelTribeExecutor`; threading is opt-in to keep old experiments reproducible by default.
- Mechanisms accept optional `time_step_days` and `days_per_month`, so monthly rates can be scaled when the engine runs daily ticks.
- `SimulationScheduler` and `DomainEvent` are the low-coupling foundation for future work: reproduction, mortality, activity assignment, and metrics can be split into smaller systems without changing the engine loop every time.
- `ReproductionMechanism` now delegates to composable policies in `simulation/reproduction.py`: mate-pool collection, weighted or strict-random mate selection, conception, pregnancy advancement, parent resolution, inheritance, and selection statistics.
- `SimulationMetrics` owns role exposure, birth/death rate, and selection-stage metric construction, reducing metric logic inside `EvolutionSimulator`.

Recommended next refactor targets:

- Split activity assignment into eligibility rules and assignment policies.
- Move metrics collection from state polling into event observers.

## Installation / 安装

```bash
pip install -r requirements.txt
```

Required:

- `numpy`
- `matplotlib` (for plotting; simulation can still run without it)

## Reproducibility Notes / 复现说明

- Use multiple random seeds and compare distribution statistics, not only single runs.
- Prefer reporting mean + median + quantiles for robustness.
- Keep configuration snapshots for each experiment when preparing reports.
