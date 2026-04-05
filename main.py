#!/usr/bin/env python3
"""
性别进化模拟系统 - 主程序
探究智人为什么是"雄稍强雌稍弱"模式
"""

import argparse
import csv
import sys
import threading
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
    CompetitionMechanism, AgingMechanism, PhenotypeAdaptationMechanism
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
        'month', 'tribe_id', 'population', 'male_count', 'female_count',
        'births', 'deaths', 'birth_rate_total', 'death_rate_total',
        'avg_male_strength', 'avg_female_strength',
        'avg_male_innate_strength', 'avg_female_innate_strength',
        'avg_male_strength_expression', 'avg_female_strength_expression',
        'selected_unique_male_rate', 'conception_per_choice', 'child_survival_5y',
        'resources', 'injured_count'
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
            sel = events.get('selection_metrics', {}).get(tid, {})
            writer.writerow({
                'month': month,
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
                'selected_unique_male_rate': sel.get('mating_stage', {}).get('selected_unique_rate', 0.0),
                'conception_per_choice': sel.get('birth_stage', {}).get('conception_per_choice', 0.0),
                'child_survival_5y': sel.get('offspring_survival_stage', {}).get('child_survival_5y', 0.0),
                'resources': tribe.total_resources,
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

    target_map = {
        'config': simulator.config,
        'activity': simulator.activity_mechanism,
        'production': simulator.production_mechanism,
        'mortality': simulator.mortality_mechanism,
        'reproduction': simulator.reproduction_mechanism,
        'distribution': simulator.distribution_mechanism,
        'adaptation': simulator.adaptation_mechanism,
        'competition': simulator.competition_mechanism
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
        elif op == 'help':
            print("命令: help | status | report | stop | checkpoint | set <scope.attr> <value> | plots")
            print("示例: set mortality.base_mortality 0.0015")
            print("示例: set runtime.report_interval 12")
        elif op == 'status':
            print(f"月份={simulator.state.month}, 部落数={len(simulator.state.tribes)}")
        elif op == 'report':
            simulator._print_progress()
        elif op == 'checkpoint':
            simulator.save_checkpoint()
        elif op == 'set' and len(parts) >= 3:
            key = parts[1]
            value_text = " ".join(parts[2:])
            _set_runtime_parameter(simulator, key, value_text, runtime_state)
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
    csv_enabled: bool = True
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
    interactive = target_months < 0
    runtime_state = {'report_interval': max(1, report_interval)}
    stop_flag = {'stop': False}
    cmd_queue: Queue = Queue()

    if interactive:
        print("\n进入持续运行模式（输入 help 查看命令，输入 stop 停止）")
        listener_thread = threading.Thread(
            target=_start_command_listener,
            args=(cmd_queue, stop_flag),
            daemon=True
        )
        listener_thread.start()

    while True:
        events = simulator.step()
        _remove_extinct_tribes(simulator)

        if csv_enabled:
            _append_monthly_csv(simulator, events, csv_path)

        if simulator.state.month % runtime_state['report_interval'] == 0:
            simulator._print_progress()

        if interactive:
            _process_commands(simulator, cmd_queue, runtime_state, stop_flag, run_dir)
            if stop_flag['stop']:
                break
        else:
            if simulator.state.month >= target_months:
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
  python main.py --months -1              # 持续运行，直到输入 stop
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
        csv_enabled=not args.no_csv
    )
    
    # 分析结果
    analyze_results(simulator)


if __name__ == '__main__':
    main()
