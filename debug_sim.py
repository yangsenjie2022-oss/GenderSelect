"""
调试模拟 - 检查各阶段状态
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from simulation.container import get_container, DIContainer
from simulation.simulator import EvolutionSimulator, SimulationConfig
from simulation.mechanisms import (
    ActivityAssignmentMechanism, ResourceProductionMechanism,
    MortalityMechanism, ReproductionMechanism, ResourceDistributionMechanism,
    CompetitionMechanism, AgingMechanism
)
from simulation.config_registry import ConfigRegistry
from simulation.models import Gender, ActivityType

# 设置容器
container = get_container()
preset = 'default'

sim_config = ConfigRegistry.create_simulation_config(preset)
container.register_instance('simulation_config', sim_config)

mech_configs = ConfigRegistry.get_mechanism_configs(preset)
container.register_instance('activity_mechanism', ActivityAssignmentMechanism(**mech_configs['activity']))
container.register_instance('production_mechanism', ResourceProductionMechanism(**mech_configs['production']))
container.register_instance('mortality_mechanism', MortalityMechanism(**mech_configs['mortality']))
container.register_instance('reproduction_mechanism', ReproductionMechanism(**mech_configs['reproduction']))
container.register_instance('distribution_mechanism', ResourceDistributionMechanism(**mech_configs['distribution']))
container.register_instance('competition_mechanism', CompetitionMechanism(**mech_configs['competition']))
container.register_instance('aging_mechanism', AgingMechanism())

# 创建模拟器
simulator = EvolutionSimulator(container)
simulator.initialize()

# 运行前几个月并打印状态
print("初始状态:")
for tid, tribe in simulator.state.tribes.items():
    print(f"  部落 {tid} ({tribe.strength_relation.name}):")
    print(f"    人口: {tribe.population} (♂{tribe.male_count}/♀{tribe.female_count})")
    print(f"    资源: 肉={tribe.food_meat:.1f}, 植物={tribe.food_plant:.1f}")

# 运行12个月（一年）
for month in range(1, 13):
    # 第一个月前详细检查
    if month == 1:
        print("\n=== 第一个月前详细检查 ===")
        for tid, tribe in simulator.state.tribes.items():
            alive = [ind for ind in tribe.individuals.values() if ind.is_alive]
            females = [ind for ind in alive if ind.gender == Gender.FEMALE]
            males = [ind for ind in alive if ind.gender == Gender.MALE]
            
            print(f"\n  部落 {tid} ({tribe.strength_relation.name}):")
            print(f"    雌性: {len(females)}")
            
            # 检查每个雌性
            for f in females[:5]:  # 只看前5个
                can_repro = f.fertility_age and not f.is_pregnant
                print(f"      ID={f.id}, age={f.age:.1f}, fertility={f.fertility_age}, pregnant={f.is_pregnant}, can_repro={can_repro}")
            
            # 检查可生育雄性
            avail_males = [m for m in males if m.fertility_age and m.resources > 5]
            print(f"    可用雄性 (fertility+resources>5): {len(avail_males)}")
    
    events = simulator.step()
    
    if month <= 3 or month % 3 == 0:
        print(f"\n--- 月份 {month} ---")
        for tid, tribe in simulator.state.tribes.items():
            alive = [ind for ind in tribe.individuals.values() if ind.is_alive]
            males = [ind for ind in alive if ind.gender == Gender.MALE]
            females = [ind for ind in alive if ind.gender == Gender.FEMALE]
            hunters = [ind for ind in alive if ind.assigned_activity == ActivityType.HUNTING]
            pregnant = [ind for ind in females if ind.is_pregnant]
            fertile = tribe.fertile_females
            
            print(f"  部落 {tid} ({tribe.strength_relation.name}):")
            print(f"    存活: {len(alive)} (♂{len(males)}/♀{len(females)}), 出生: {events['births'][tid]}, 死亡: {events['deaths'][tid]}")
            print(f"    猎人: {len(hunters)}, 可生育雌性: {len(fertile)}, 怀孕: {len(pregnant)}")
            print(f"    资源: 肉={tribe.food_meat:.1f}, 植物={tribe.food_plant:.1f}, 总资源={tribe.total_resources:.1f}")
