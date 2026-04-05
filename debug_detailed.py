import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from simulation.container import get_container
from simulation.simulator import EvolutionSimulator
from simulation.config_registry import ConfigRegistry
from simulation.mechanisms import *
from simulation.models import Gender, ActivityType
import numpy as np

np.random.seed(42)  # 固定随机种子

container = get_container()
sim_config = ConfigRegistry.create_simulation_config('abundant_environment')
container.register_instance('simulation_config', sim_config)
mech_configs = ConfigRegistry.get_mechanism_configs('abundant_environment')

container.register_instance('activity_mechanism', ActivityAssignmentMechanism(**mech_configs['activity']))
container.register_instance('production_mechanism', ResourceProductionMechanism(**mech_configs['production']))
container.register_instance('mortality_mechanism', MortalityMechanism(**mech_configs['mortality']))
container.register_instance('reproduction_mechanism', ReproductionMechanism(**mech_configs['reproduction']))
container.register_instance('distribution_mechanism', ResourceDistributionMechanism(**mech_configs['distribution']))
container.register_instance('competition_mechanism', CompetitionMechanism(**mech_configs['competition']))
container.register_instance('aging_mechanism', AgingMechanism())

sim = EvolutionSimulator(container)
sim.config = sim_config
sim.initialize()

# Run 15 months with detailed death tracking
for m in range(15):
    pre_pop = {tid: tribe.population for tid, tribe in sim.state.tribes.items()}
    events = sim.step()
    post_pop = {tid: tribe.population for tid, tribe in sim.state.tribes.items()}
    
    if m >= 8:  # 从第9个月开始详细输出
        print(f'\n=== Month {m+1} ===')
        for tid in sim.state.tribes.keys():
            change = post_pop[tid] - pre_pop[tid]
            print(f'Tribe {tid}: {pre_pop[tid]} -> {post_pop[tid]} (change: {change:+d})')
            print(f'  Births: {events["births"][tid]}, Deaths: {events["deaths"][tid]}')
            
            tribe = sim.state.tribes[tid]
            alive = [ind for ind in tribe.individuals.values() if ind.is_alive]
            hunters = [ind for ind in alive if ind.assigned_activity == ActivityType.HUNTING]
            females = [ind for ind in alive if ind.gender == Gender.FEMALE]
            pregnant = [ind for ind in females if ind.is_pregnant]
            print(f'  Alive: {len(alive)}, Hunters: {len(hunters)}, Females: {len(females)}, Pregnant: {len(pregnant)}')
