#!/usr/bin/env python3
"""
快速运行脚本 - 预置常用场景
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from main import run_simulation, analyze_results, list_presets


def quick_run():
    """快速运行默认场景"""
    print("="*70)
    print("性别进化模拟系统 - 快速运行")
    print("探究: 为什么智人是'雄稍强雌稍弱'模式")
    print("="*70)
    
    # 列出可用预设
    list_presets()
    
    # 运行默认场景
    print("\n>>> 运行默认场景 (balanced parameters)\n")
    simulator = run_simulation(preset='default', output_dir='./output/default')
    analyze_results(simulator)
    
    return simulator


def compare_scenarios():
    """对比不同环境条件下的结果"""
    print("="*70)
    print("场景对比分析")
    print("="*70)
    
    scenarios = ['default', 'harsh_environment', 'abundant_environment', 'intense_competition']
    results = []
    
    for preset in scenarios:
        print(f"\n>>> 运行场景: {preset}")
        simulator = run_simulation(preset=preset, output_dir=f'./output/{preset}')
        
        # 记录胜者
        if simulator.state.tribes:
            winner = max(simulator.state.tribes.values(), 
                        key=lambda t: t.population)
            results.append({
                'scenario': preset,
                'winner': winner.strength_relation.name,
                'population': winner.population,
                'survival_rate': winner.population / max(1, winner.birth_count + winner.population) * 100
            })
    
    # 打印对比结果
    print("\n" + "="*70)
    print("场景对比总结")
    print("="*70)
    print(f"{'场景':<20} {'胜者':<25} {'人口':<10} {'存活率':<10}")
    print("-"*70)
    for r in results:
        print(f"{r['scenario']:<20} {r['winner']:<25} {r['population']:<10} {r['survival_rate']:<10.1f}%")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='快速运行模拟')
    parser.add_argument('--compare', '-c', action='store_true',
                       help='运行多个场景对比')
    parser.add_argument('--preset', '-p', type=str,
                       help='指定预设运行')
    
    args = parser.parse_args()
    
    if args.compare:
        compare_scenarios()
    elif args.preset:
        simulator = run_simulation(preset=args.preset, output_dir=f'./output/{args.preset}')
        analyze_results(simulator)
    else:
        quick_run()
