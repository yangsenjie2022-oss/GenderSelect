import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from simulation.container import get_container
from simulation.simulator import EvolutionSimulator
from simulation.config_registry import ConfigRegistry
from simulation.mechanisms import *
from simulation.models import Gender, ActivityType
import numpy as np

np.random.seed(42)

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

# Run 10 months
for m in range(10):
    sim.step()

print('=== Before Month 11 step ===')
for tid, tribe in sim.state.tribes.items():
    alive = [ind for ind in tribe.individuals.values() if ind.is_alive]
    print(f'\nTribe {tid}: {len(alive)} alive')
    for ind in alive[:5]:  # 只看前5个
        print(f'  ID={ind.id}, age={ind.age:.1f}, health={ind.health:.2f}, resources={ind.resources:.2f}, activity={ind.assigned_activity}')

# Now do Month 11 step manually to see what happens
print('\n=== Month 11 step ===')

# 1. Activity assignment
for tribe in sim.state.tribes.values():
    sim.activity_mechanism.apply(tribe)

# 2. Resource production  
for tribe in sim.state.tribes.values():
    sim.production_mechanism.apply(tribe)

# 3. Resource distribution
for tribe in sim.state.tribes.values():
    sim.distribution_mechanism.apply(tribe)

print('After production and distribution:')
for tid, tribe in sim.state.tribes.items():
    print(f'  Tribe {tid}: resources={tribe.total_resources:.1f}')

# 4. Reproduction
for tribe in sim.state.tribes.values():
    newborns, _, _ = sim.reproduction_mechanism.apply(tribe, 1000)
    print(f'  Tribe {tid}: {len(newborns)} newborns')

# 5. Aging
for tribe in sim.state.tribes.values():
    sim.aging_mechanism.apply(tribe)

# 6. Check before mortality
print('\nBefore mortality:')
for tid, tribe in sim.state.tribes.items():
    alive = [ind for ind in tribe.individuals.values() if ind.is_alive]
    print(f'  Tribe {tid}: {len(alive)} alive')

# 6. Mortality
print('\nMortality check:')
for tid, tribe in sim.state.tribes.items():
    deceased = sim.mortality_mechanism.apply(tribe)
    print(f'  Tribe {tid}: {len(deceased)} deaths')
    for ind in deceased[:5]:
        print(f'    ID={ind.id}, age={ind.age:.1f}, health={ind.health:.2f}, resources={ind.resources:.2f}')

# 7. Check after mortality
print('\nAfter mortality:')
for tid, tribe in sim.state.tribes.items():
    alive = [ind for ind in tribe.individuals.values() if ind.is_alive]
    print(f'  Tribe {tid}: {len(alive)} alive')
