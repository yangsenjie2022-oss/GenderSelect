#!/usr/bin/env python3
"""
性别进化模拟系统 - 主程序
探究智人为什么是"雄稍强雌稍弱"模式
"""

import argparse
import csv
import sys
import threading
import time
from queue import Queue, Empty
from datetime import datetime
from pathlib import Path

# 确保可以导入simulation模块
sys.path.insert(0, str(Path(__file__).parent))

from simulation.container import get_container, DIContainer
from simulation.simulator import EvolutionSimulator, SimulationConfig
from simulation.mechanisms import (
    ActivityAssignmentMechanism, ResourceProductionMechanism,
    MortalityMechanism, ReproductionMechanism, ResourceDistributionMechanism,
    CompetitionMechanism, BeastAttackMechanism, AgingMechanism, PhenotypeAdaptationMechanism
)
from simulation.config_registry import ConfigRegistry


def _make_run_output_dir(output_dir: str, run_name: str = None) -> Path:
    """创建本次运行输出目录"""
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    if run_name is None or not str(run_name).strip():
        run_name = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = base / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _try_parse_value(text: str):
    """命令行字符串转 Python 值"""
    t = text.strip()
    low = t.lower()
    if low in ('true', 'false'):
        return low == 'true'
    try:
        if any(c in t for c in ['.', 'e', 'E']):
            return float(t)
        return int(t)
    except ValueError:
        return t


def _append_monthly_csv(simulator: EvolutionSimulator, events: dict, csv_path: Path):
    """按月写 CSV（每部落一行）"""
    fields = [
        'month', 'day', 'time_unit', 'tribe_id', 'population', 'male_count', 'female_count',
        'births', 'deaths', 'birth_rate_total', 'death_rate_total',
        'avg_male_strength', 'avg_female_strength',
        'avg_male_innate_strength', 'avg_female_innate_strength',
        'avg_male_strength_expression', 'avg_female_strength_expression',
        'male_hunter_ratio', 'female_hunter_ratio',
        'male_gatherer_ratio', 'female_gatherer_ratio',
        'male_crafter_ratio', 'female_crafter_ratio',
        'selected_unique_male_rate', 'conception_per_choice', 'child_survival_5y',
        'resources', 'tool_material', 'stone_tools', 'injured_count'
    ]
    is_new = not csv_path.exists()
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if is_new:
            writer.writeheader()
        month = simulator.state.month
        for tid, tribe in simulator.state.tribes.items():
            rate_b = events.get('birth_rates', {}).get(tid, {})
            rate_d = events.get('death_rates', {}).get(tid, {})
            role = events.get('role_exposure', {}).get(tid, {})
            sel = events.get('selection_metrics', {}).get(tid, {})
            writer.writerow({
                'month': month,
                'day': events.get('day', getattr(simulator.state, 'day', month * 30)),
                'time_unit': events.get('time_unit', getattr(simulator.config, 'time_unit', 'month')),
                'tribe_id': tid,
                'population': tribe.population,
                'male_count': tribe.male_count,
                'female_count': tribe.female_count,
                'births': events.get('births', {}).get(tid, 0),
                'deaths': events.get('deaths', {}).get(tid, 0),
                'birth_rate_total': rate_b.get('total', 0.0),
                'death_rate_total': rate_d.get('total', 0.0),
                'avg_male_strength': tribe.avg_male_strength,
                'avg_female_strength': tribe.avg_female_strength,
                'avg_male_innate_strength': tribe.avg_male_innate_strength,
                'avg_female_innate_strength': tribe.avg_female_innate_strength,
                'avg_male_strength_expression': tribe.avg_male_strength_expression,
                'avg_female_strength_expression': tribe.avg_female_strength_expression,
                'male_hunter_ratio': role.get('male_hunter_ratio', 0.0),
                'female_hunter_ratio': role.get('female_hunter_ratio', 0.0),
                'male_gatherer_ratio': role.get('male_gatherer_ratio', 0.0),
                'female_gatherer_ratio': role.get('female_gatherer_ratio', 0.0),
                'male_crafter_ratio': role.get('male_crafter_ratio', 0.0),
                'female_crafter_ratio': role.get('female_crafter_ratio', 0.0),
                'selected_unique_male_rate': sel.get('mating_stage', {}).get('selected_unique_rate', 0.0),
                'conception_per_choice': sel.get('birth_stage', {}).get('conception_per_choice', 0.0),
                'child_survival_5y': sel.get('offspring_survival_stage', {}).get('child_survival_5y', 0.0),
                'resources': tribe.total_resources,
                'tool_material': tribe.tool_material,
                'stone_tools': tribe.stone_tools,
                'injured_count': tribe.injured_count
            })


def _remove_extinct_tribes(simulator: EvolutionSimulator):
    """清理灭绝部落（与原 run() 行为一致）"""
    extinct = [tid for tid, tribe in simulator.state.tribes.items() if tribe.population <= 0]
    for tid in extinct:
        print(f"部落 {tid} 已灭绝")
        del simulator.state.tribes[tid]


def _set_runtime_parameter(simulator: EvolutionSimulator, key: str, value_text: str, runtime_state: dict) -> bool:
    """
    运行时参数注入:
    - runtime.report_interval
    - config.xxx
    - activity.xxx / production.xxx / mortality.xxx / reproduction.xxx
    - distribution.xxx / adaptation.xxx / competition.xxx
    """
    value = _try_parse_value(value_text)
    if key == 'runtime.report_interval':
        runtime_state['report_interval'] = max(1, int(value))
        print(f"[runtime] report_interval = {runtime_state['report_interval']}")
        return True
    if key == 'runtime.paused':
        runtime_state['paused'] = bool(value)
        print(f"[runtime] paused = {runtime_state['paused']}")
        return True

    target_map = {
        'config': simulator.config,
        'activity': simulator.activity_mechanism,
        'production': simulator.production_mechanism,
        'mortality': simulator.mortality_mechanism,
        'reproduction': simulator.reproduction_mechanism,
        'distribution': simulator.distribution_mechanism,
        'adaptation': simulator.adaptation_mechanism,
        'competition': simulator.competition_mechanism,
        'beast': simulator.beast_attack_mechanism
    }
    if '.' not in key:
        print("参数格式错误，应为 scope.attr，例如 mortality.base_mortality")
        return False
    scope, attr = key.split('.', 1)
    obj = target_map.get(scope)
    if obj is None:
        print(f"未知 scope: {scope}")
        return False
    if not hasattr(obj, attr):
        print(f"{scope} 无参数: {attr}")
        return False
    setattr(obj, attr, value)
    print(f"[runtime] {scope}.{attr} = {value}")
    return True


def _apply_runtime_strategy(simulator: EvolutionSimulator, preset_name: str):
    """运行时应用某个预设策略（只覆盖机制/配置中已有字段）"""
    if preset_name not in ConfigRegistry.get_preset_names():
        raise ValueError(f"未知预设: {preset_name}")
    cfg = ConfigRegistry.get_mechanism_configs(preset_name)
    mech_map = {
        'activity': simulator.activity_mechanism,
        'production': simulator.production_mechanism,
        'mortality': simulator.mortality_mechanism,
        'reproduction': simulator.reproduction_mechanism,
        'distribution': simulator.distribution_mechanism,
        'adaptation': simulator.adaptation_mechanism,
        'competition': simulator.competition_mechanism,
        'beast': simulator.beast_attack_mechanism,
    }
    updated = 0
    for scope, params in cfg.items():
        obj = mech_map.get(scope)
        if obj is None:
            continue
        for k, v in params.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
                updated += 1
    print(f"[runtime] 已应用策略: {preset_name}, 更新参数数={updated}")


def _start_command_listener(cmd_queue: Queue, stop_flag: dict):
    """后台命令读取线程"""
    while not stop_flag.get('stop', False):
        try:
            line = input().strip()
        except EOFError:
            stop_flag['stop'] = True
            break
        if line:
            cmd_queue.put(line)


def _process_commands(simulator: EvolutionSimulator, cmd_queue: Queue, runtime_state: dict, stop_flag: dict, run_dir: Path):
    """处理运行时命令"""
    while True:
        try:
            cmd = cmd_queue.get_nowait()
        except Empty:
            break
        parts = cmd.split()
        if not parts:
            continue
        op = parts[0].lower()
        if op in ('stop', 'quit', 'exit'):
            stop_flag['stop'] = True
            print("收到停止命令，将在当前月结束后退出。")
        elif op in ('p', 'pause'):
            runtime_state['paused'] = True
            print("已暂停。可输入 set/strategy/status/report/plots/checkpoint，输入 resume 继续。")
        elif op in ('r', 'resume'):
            runtime_state['paused'] = False
            print("继续运行。")
        elif op == 'help':
            print("命令: help | p(pause) | r(resume) | status | report | stop | checkpoint | plots")
            print("      set <scope.attr> <value> | strategy <preset_name>")
            print("示例: set mortality.base_mortality 0.0015")
            print("示例: set runtime.report_interval 12")
            print("示例: strategy ablation_symmetric_hunt_risk")
        elif op == 'status':
            print(f"月份={simulator.state.month}, 部落数={len(simulator.state.tribes)}, paused={runtime_state.get('paused', False)}")
        elif op == 'report':
            simulator._print_progress()
        elif op == 'checkpoint':
            simulator.save_checkpoint()
        elif op == 'set' and len(parts) >= 3:
            key = parts[1]
            value_text = " ".join(parts[2:])
            _set_runtime_parameter(simulator, key, value_text, runtime_state)
        elif op == 'strategy' and len(parts) >= 2:
            preset_name = parts[1]
            try:
                _apply_runtime_strategy(simulator, preset_name)
            except Exception as e:
                print(f"策略应用失败: {e}")
        elif op == 'plots':
            try:
                from simulation.visualization import SimulationVisualizer
                viz = SimulationVisualizer(str(run_dir))
                viz.generate_all_plots(simulator.state)
                print("已生成当前阶段图表。")
            except Exception as e:
                print(f"图表生成失败: {e}")
        else:
            print(f"未知命令: {cmd}")


def setup_container(preset_name: str = 'default') -> DIContainer:
    """
    设置依赖注入容器
    所有组件都通过容器解析，便于替换和测试
    """
    container = get_container()
    
    # 1. 注册配置
    sim_config = ConfigRegistry.create_simulation_config(preset_name)
    container.register_instance('simulation_config', sim_config)
    
    # 2. 注册机制（依赖注入）
    mech_configs = ConfigRegistry.get_mechanism_configs(preset_name)
    
    container.register_instance(
        'activity_mechanism',
        ActivityAssignmentMechanism(**mech_configs['activity'])
    )
    
    container.register_instance(
        'production_mechanism',
        ResourceProductionMechanism(**mech_configs['production'])
    )
    
    container.register_instance(
        'mortality_mechanism',
        MortalityMechanism(**mech_configs['mortality'])
    )
    
    container.register_instance(
        'reproduction_mechanism',
        ReproductionMechanism(**mech_configs['reproduction'])
    )
    
    container.register_instance(
        'distribution_mechanism',
        ResourceDistributionMechanism(**mech_configs['distribution'])
    )

    adaptation_cfg = mech_configs.get('adaptation', {})
    container.register_instance(
        'adaptation_mechanism',
        PhenotypeAdaptationMechanism(**adaptation_cfg)
    )
    
    container.register_instance(
        'competition_mechanism',
        CompetitionMechanism(**mech_configs['competition'])
    )

    beast_cfg = mech_configs.get('beast', {})
    container.register_instance(
        'beast_attack_mechanism',
        BeastAttackMechanism(**beast_cfg)
    )
    
    container.register_instance(
        'aging_mechanism',
        AgingMechanism()
    )
    
    return container


def run_simulation(
    preset: str = 'default',
    months: int = None,
    checkpoint: str = None,
    output_dir: str = './output',
    run_name: str = None,
    report_interval: int = 12,
    csv_enabled: bool = True,
    live_control: bool = False,
    time_unit: str = None,
    days_per_month: int = None,
    parallel_enabled: bool = None,
    max_workers: int = None
) -> EvolutionSimulator:
    """
    运行模拟
    
    Args:
        preset: 预设配置名称
        months: 模拟月数（覆盖预设）
        checkpoint: 从检查点继续的选项（'auto' 或具体路径）
        output_dir: 输出目录
    """
    print(f"\n{'='*60}")
    print("性别进化模拟系统")
    print(f"预设: {preset} - {ConfigRegistry.get_preset_description(preset)}")
    print(f"{'='*60}\n")
    
    # 1. 设置容器
    container = setup_container(preset)
    
    # 2. 创建模拟器
    simulator = EvolutionSimulator(container)

    def _apply_engine_runtime_config():
        # 运行级框架配置（不改变预设文件本身）
        if time_unit is not None:
            simulator.config.time_unit = time_unit
        if days_per_month is not None:
            simulator.config.days_per_month = max(1, int(days_per_month))
        if parallel_enabled is not None:
            simulator.config.parallel_enabled = bool(parallel_enabled)
        if max_workers is not None:
            simulator.config.max_workers = max(1, int(max_workers))
        simulator._refresh_execution()

    _apply_engine_runtime_config()
    
    # 3. 加载检查点或初始化
    if checkpoint:
        if checkpoint == 'auto':
            # 自动查找最新检查点
            checkpoint_dir = Path(simulator.config.checkpoint_dir)
            checkpoints = sorted(checkpoint_dir.glob("checkpoint_month_*.pkl"))
            if checkpoints:
                checkpoint = str(checkpoints[-1])
            else:
                print("未找到检查点，开始新模拟")
                checkpoint = None
        
        if checkpoint:
            simulator.load_checkpoint(checkpoint)
            _apply_engine_runtime_config()
    
    if not checkpoint:
        simulator.initialize()
    
    # 4. 运行目录（每次可独立命名）
    run_dir = _make_run_output_dir(output_dir, run_name)
    csv_path = run_dir / "monthly_stats.csv"
    print(f"输出目录: {run_dir}")
    if csv_enabled:
        print(f"CSV文件: {csv_path}")

    # 5. 运行模拟（months < 0 表示持续运行，直到 stop 命令）
    target_months = simulator.config.max_simulation_months if months is None else months
    interactive = (target_months < 0) or live_control
    runtime_state = {'report_interval': max(1, report_interval), 'paused': False}
    stop_flag = {'stop': False}
    cmd_queue: Queue = Queue()

    if interactive:
        print("\n进入运行时控制模式（输入 help 查看命令，输入 p 暂停，stop 停止）")
        listener_thread = threading.Thread(
            target=_start_command_listener,
            args=(cmd_queue, stop_flag),
            daemon=True
        )
        listener_thread.start()

    while True:
        if interactive:
            _process_commands(simulator, cmd_queue, runtime_state, stop_flag, run_dir)
            if stop_flag['stop']:
                break
            if runtime_state.get('paused', False):
                time.sleep(0.15)
                continue

        events = simulator.step()
        _remove_extinct_tribes(simulator)

        if csv_enabled:
            _append_monthly_csv(simulator, events, csv_path)

        if getattr(simulator.config, 'time_unit', 'month') == 'day':
            report_due = (
                simulator.state.day > 0 and
                simulator.state.day % (
                    runtime_state['report_interval'] * max(1, getattr(simulator.config, 'days_per_month', 30))
                ) == 0
            )
        else:
            report_due = simulator.state.month % runtime_state['report_interval'] == 0

        if report_due:
            simulator._print_progress()

        if not interactive:
            if simulator.state.month >= target_months:
                break
        else:
            if target_months >= 0 and simulator.state.month >= target_months:
                break

    print(f"模拟结束，月份: {simulator.state.month}")
    simulator._print_final_stats()

    # 6. 生成可视化（缺少 matplotlib 时不阻塞主流程）
    try:
        from simulation.visualization import SimulationVisualizer
        visualizer = SimulationVisualizer(str(run_dir))
        visualizer.generate_all_plots(simulator.state)
    except Exception as e:
        print(f"可视化生成失败（已跳过）: {e}")
    
    return simulator


def list_presets():
    """列出所有可用预设"""
    print("\n可用预设配置:")
    print("-" * 50)
    for name in ConfigRegistry.get_preset_names():
        desc = ConfigRegistry.get_preset_description(name)
        print(f"  {name:25s} - {desc}")
    print()


def analyze_results(simulator: EvolutionSimulator):
    """分析并打印模拟结果"""
    print(f"\n{'='*60}")
    print("模拟结果分析")
    print(f"{'='*60}\n")
    
    results = simulator.get_results()
    structure = results.get('population_structure', 'isolated_relation_tribes')
    
    # 找出获胜者
    tribes = results['tribes']
    if not tribes:
        print("所有部落都已灭绝")
        return
    
    # 按人口排序
    sorted_tribes = sorted(tribes.items(), 
                          key=lambda x: x[1]['final_population'], 
                          reverse=True)
    
    print("最终排名:")
    print("-" * 50)
    for i, (tid, data) in enumerate(sorted_tribes, 1):
        pop = data['final_population']
        births = data['birth_count']
        deaths = data['death_count']
        injured = data.get('injured_count', 0)
        avg_male_strength = data.get('avg_male_strength', 0.0)  # 后天表现型
        avg_female_strength = data.get('avg_female_strength', 0.0)
        median_male_strength = data.get('median_male_strength', 0.0)
        median_female_strength = data.get('median_female_strength', 0.0)
        avg_male_innate_strength = data.get('avg_male_innate_strength', 0.0)
        avg_female_innate_strength = data.get('avg_female_innate_strength', 0.0)
        avg_male_strength_expression = data.get('avg_male_strength_expression', 1.0)
        avg_female_strength_expression = data.get('avg_female_strength_expression', 1.0)
        median_male_innate_strength = data.get('median_male_innate_strength', 0.0)
        median_female_innate_strength = data.get('median_female_innate_strength', 0.0)
        pref = data.get('female_mate_preference_ratios', {})
        survival = pop / max(1, births + pop) * 100
        
        print(f"{i}. Tribe {tid}")
        print(f"   人口: {pop}")
        print(f"   出生: {births} | 死亡: {deaths}")
        print(
            f"   出生率(总/雄/雌): {data.get('avg_birth_rate_total', 0.0):.3f} / "
            f"{data.get('avg_birth_rate_male', 0.0):.3f} / {data.get('avg_birth_rate_female', 0.0):.3f}"
        )
        print(
            f"   死亡率(总/雄/雌): {data.get('avg_death_rate_total', 0.0):.3f} / "
            f"{data.get('avg_death_rate_male', 0.0):.3f} / {data.get('avg_death_rate_female', 0.0):.3f}"
        )
        print(
            f"   后天力量(含表达 均值 雄/雌): {avg_male_strength:.3f} / {avg_female_strength:.3f} | "
            f"中位数: {median_male_strength:.3f} / {median_female_strength:.3f}"
        )
        print(
            f"   先天力量(均值 雄/雌): {avg_male_innate_strength:.3f} / {avg_female_innate_strength:.3f} | "
            f"中位数: {median_male_innate_strength:.3f} / {median_female_innate_strength:.3f}"
        )
        print(
            f"   力量表达基因(雄体/雌体): {avg_male_strength_expression:.3f} / "
            f"{avg_female_strength_expression:.3f}"
        )
        print(
            "   雌性择偶偏好占比(资/力/智/沟/均衡): "
            f"{pref.get('resource', 0.0):.2f} / {pref.get('strength', 0.0):.2f} / "
            f"{pref.get('intelligence', 0.0):.2f} / {pref.get('communication', 0.0):.2f} / "
            f"{pref.get('balanced', 0.0):.2f}"
        )
        print(f"   雌性主导偏好: {data.get('dominant_female_mate_preference', 'balanced')}")
        print(
            f"   三阶段选择(配偶/受孕/幼体5岁存活): "
            f"{data.get('avg_selected_unique_male_rate', 0.0):.3f} / "
            f"{data.get('avg_conception_per_choice', 0.0):.3f} / "
            f"{data.get('avg_child_survival_5y', 0.0):.3f}"
        )
        print(
            f"   分工暴露(雄猎/雌猎/雄采/雌采): "
            f"{data.get('avg_male_hunter_ratio', 0.0):.3f} / "
            f"{data.get('avg_female_hunter_ratio', 0.0):.3f} / "
            f"{data.get('avg_male_gatherer_ratio', 0.0):.3f} / "
            f"{data.get('avg_female_gatherer_ratio', 0.0):.3f}"
        )
        print(
            f"   工匠暴露(雄工/雌工): "
            f"{data.get('avg_male_crafter_ratio', 0.0):.3f} / "
            f"{data.get('avg_female_crafter_ratio', 0.0):.3f}"
        )
        print(
            f"   工具库存(石料/石器): "
            f"{data.get('final_tool_material', 0.0):.1f} / "
            f"{data.get('final_stone_tools', 0.0):.1f}"
        )
        print(f"   当前受伤: {injured}")
        print(f"   存活率: {survival:.1f}%")
        print()
    
    print(f"群体结构模式: {structure}")


def main():
    parser = argparse.ArgumentParser(
        description='性别进化模拟系统 - 探究智人的性别强弱关系',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                          # 使用默认配置运行
  python main.py --preset harsh_environment  # 使用恶劣环境配置
  python main.py --list-presets           # 列出所有预设
  python main.py --checkpoint auto        # 从最新检查点继续
  python main.py --months 500             # 只运行500个月
  python main.py --months 12 --time-unit day  # 以天为tick运行12个月
  python main.py --parallel --max-workers 4   # 按部落并行执行可并行阶段
  python main.py --months -1              # 持续运行，直到输入 stop
  python main.py --months 500 --live-control  # 有限月数 + 运行时命令控制
  python main.py --run-name exp_01        # 本次输出写入 output/exp_01/
        """
    )
    
    parser.add_argument('--preset', '-p', type=str, default='default',
                       help='使用预设配置 (默认: default)')
    parser.add_argument('--list-presets', '-l', action='store_true',
                       help='列出所有可用预设')
    parser.add_argument('--months', '-m', type=int,
                       help='模拟月数（覆盖预设）')
    parser.add_argument('--checkpoint', '-c', type=str,
                       help='从检查点继续 (auto=自动查找最新)')
    parser.add_argument('--output', '-o', type=str, default='./output',
                       help='输出目录 (默认: ./output)')
    parser.add_argument('--run-name', type=str,
                       help='本次运行子目录名称（不填则自动时间戳）')
    parser.add_argument('--report-interval', type=int, default=12,
                       help='进度报表间隔（月，默认: 12）')
    parser.add_argument('--no-csv', action='store_true',
                       help='禁用每月CSV写入')
    parser.add_argument('--live-control', action='store_true',
                       help='启用运行时命令控制（输入 p 暂停并注入命令）')
    parser.add_argument('--time-unit', choices=['month', 'day'],
                       help='模拟tick粒度：month=每步一月，day=每步一天')
    parser.add_argument('--days-per-month', type=int,
                       help='日粒度下每月天数（默认由配置决定，通常为30）')
    parser.add_argument('--parallel', action='store_true',
                       help='开启按部落并行执行可并行阶段')
    parser.add_argument('--max-workers', type=int,
                       help='并行worker数量')
    parser.add_argument('--analyze-only', '-a', type=str, metavar='CHECKPOINT',
                       help='只分析已有检查点，不运行模拟')
    
    args = parser.parse_args()
    
    # 列出预设
    if args.list_presets:
        list_presets()
        return
    
    # 只分析
    if args.analyze_only:
        container = setup_container('default')
        simulator = EvolutionSimulator(container)
        if simulator.load_checkpoint(args.analyze_only):
            try:
                from simulation.visualization import SimulationVisualizer
                visualizer = SimulationVisualizer(args.output)
                visualizer.generate_all_plots(simulator.state)
            except Exception as e:
                print(f"可视化生成失败（已跳过）: {e}")
            analyze_results(simulator)
        return
    
    # 运行模拟
    simulator = run_simulation(
        preset=args.preset,
        months=args.months,
        checkpoint=args.checkpoint,
        output_dir=args.output,
        run_name=args.run_name,
        report_interval=args.report_interval,
        csv_enabled=not args.no_csv,
        live_control=args.live_control,
        time_unit=args.time_unit,
        days_per_month=args.days_per_month,
        parallel_enabled=args.parallel if args.parallel else None,
        max_workers=args.max_workers
    )
    
    # 分析结果
    analyze_results(simulator)


if __name__ == '__main__':
    main()
