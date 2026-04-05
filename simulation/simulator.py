"""
模拟引擎 - 协调所有机制运行
"""
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, field
import numpy as np
import pickle
import os
from datetime import datetime

from .models import Tribe, Individual, GenderStrengthRelation, Gender
from .mechanisms import (
    BaseMechanism, ActivityAssignmentMechanism, ResourceProductionMechanism,
    MortalityMechanism, ReproductionMechanism, ResourceDistributionMechanism,
    CompetitionMechanism, AgingMechanism, PhenotypeAdaptationMechanism
)
from .container import DIContainer


@dataclass
class SimulationConfig:
    """模拟配置"""
    # 人口参数
    initial_population: int = 50
    max_simulation_months: int = 1200  # 100年
    
    # K值（环境承载力）
    base_k: float = 200
    
    # 人口结构模式：多部落 + 能力连续分布（默认）
    population_structure: str = "ability_multi_tribe"
    tribe_count: int = 4
    # 部落分裂参数
    split_population_threshold: int = 600
    split_probability_full_population: int = 1000
    split_ratio_sigma: float = 0.12
    split_peer_population_ratio_low: float = 0.8
    split_peer_population_ratio_high: float = 1.25
    split_min_child_vs_opponent_ratio: float = 0.6
    
    # 检查点配置
    checkpoint_interval: int = 100
    checkpoint_dir: str = "./checkpoints"


@dataclass 
class SimulationState:
    """模拟状态（可序列化）"""
    month: int = 0
    tribes: Dict[int, Tribe] = field(default_factory=dict)
    individual_id_counter: int = 0
    next_tribe_id: int = 0
    history: List[Dict] = field(default_factory=list)
    
    def __getstate__(self):
        return {
            'month': self.month,
            'tribes': {k: v.to_dict() for k, v in self.tribes.items()},
            'individual_id_counter': self.individual_id_counter,
            'next_tribe_id': self.next_tribe_id,
            'history': self.history
        }
    
    def __setstate__(self, state):
        self.month = state['month']
        self.tribes = {int(k): Tribe.from_dict(v) for k, v in state['tribes'].items()}
        self.individual_id_counter = state['individual_id_counter']
        self.next_tribe_id = state.get('next_tribe_id', (max(self.tribes.keys()) + 1 if self.tribes else 0))
        self.history = state['history']


class EvolutionSimulator:
    """进化模拟器"""
    
    def __init__(self, container: Optional[DIContainer] = None):
        self.container = container or DIContainer()
        self.config: SimulationConfig = None
        self.state: SimulationState = SimulationState()
        
        # 机制实例（通过依赖注入）
        self.activity_mechanism: ActivityAssignmentMechanism = None
        self.production_mechanism: ResourceProductionMechanism = None
        self.mortality_mechanism: MortalityMechanism = None
        self.reproduction_mechanism: ReproductionMechanism = None
        self.distribution_mechanism: ResourceDistributionMechanism = None
        self.adaptation_mechanism: PhenotypeAdaptationMechanism = None
        self.competition_mechanism: CompetitionMechanism = None
        self.aging_mechanism: AgingMechanism = None
        
        # 事件回调
        self.event_callbacks: List[Callable[[str, Dict], None]] = []
        
        self._resolve_dependencies()
        self.initial_tribe_count: int = 0
    
    def _resolve_dependencies(self):
        """解析依赖"""
        # 尝试从容器解析各机制
        try:
            self.activity_mechanism = self.container.resolve('activity_mechanism')
        except:
            self.activity_mechanism = ActivityAssignmentMechanism()
        
        try:
            self.production_mechanism = self.container.resolve('production_mechanism')
        except:
            self.production_mechanism = ResourceProductionMechanism()
        
        try:
            self.mortality_mechanism = self.container.resolve('mortality_mechanism')
        except:
            self.mortality_mechanism = MortalityMechanism()
        
        try:
            self.reproduction_mechanism = self.container.resolve('reproduction_mechanism')
        except:
            self.reproduction_mechanism = ReproductionMechanism()
        
        try:
            self.distribution_mechanism = self.container.resolve('distribution_mechanism')
        except:
            self.distribution_mechanism = ResourceDistributionMechanism()

        try:
            self.adaptation_mechanism = self.container.resolve('adaptation_mechanism')
        except:
            self.adaptation_mechanism = PhenotypeAdaptationMechanism()
        
        try:
            self.competition_mechanism = self.container.resolve('competition_mechanism')
        except:
            self.competition_mechanism = CompetitionMechanism()
        
        try:
            self.aging_mechanism = self.container.resolve('aging_mechanism')
        except:
            self.aging_mechanism = AgingMechanism()
        
        # 解析配置
        try:
            self.config = self.container.resolve('simulation_config')
        except:
            self.config = SimulationConfig()
    
    def initialize(self, config: Optional[SimulationConfig] = None):
        """初始化模拟"""
        if config:
            self.config = config
        
        self.state = SimulationState()
        self.initial_tribe_count = self.config.tribe_count

        self._initialize_ability_multi_tribe()
        
        self._emit_event('initialized', {
            'population_structure': self.config.population_structure,
            'tribes': {k: {'pop': v.population, 'injured': v.injured_count}
                      for k, v in self.state.tribes.items()}
        })

    def _initialize_ability_multi_tribe(self):
        """能力驱动初始化：多个部落，连续能力分布，不预设三类群体"""
        tribe_count = max(2, self.config.tribe_count)
        base_pop = self.config.initial_population // tribe_count
        remainder = self.config.initial_population % tribe_count

        for tribe_id in range(tribe_count):
            tribe = Tribe(id=tribe_id, strength_relation=GenderStrengthRelation.EQUAL)
            pop = base_pop + (1 if tribe_id < remainder else 0)
            self._seed_tribe_population(tribe, pop)
            self._seed_tribe_resources(tribe)
            self.state.tribes[tribe_id] = tribe
        self.state.next_tribe_id = tribe_count

    def _seed_tribe_population(self, tribe: Tribe, pop: int):
        """初始化部落人口（能力连续分布）"""
        males = pop // 2
        females = pop - males
        for _ in range(males):
            ind = Individual(
                id=self.state.individual_id_counter,
                gender=Gender.MALE,
                strength_relation=GenderStrengthRelation.EQUAL,
                age=np.random.randint(20, 30)
            )
            tribe.add_individual(ind)
            self.state.individual_id_counter += 1

        for _ in range(females):
            ind = Individual(
                id=self.state.individual_id_counter,
                gender=Gender.FEMALE,
                strength_relation=GenderStrengthRelation.EQUAL,
                age=np.random.randint(20, 30)
            )
            tribe.add_individual(ind)
            self.state.individual_id_counter += 1

    def _seed_tribe_resources(self, tribe: Tribe):
        """初始化部落资源"""
        tribe.food_meat = 100
        tribe.food_plant = 100
        tribe.total_resources = 200

    def step(self) -> Dict:
        """执行一步模拟（一个月）"""
        self.state.month += 1
        current_month = self.state.month

        # 记录月初人口，用于计算当月出生率/死亡率
        month_start = {
            tid: {
                'population': tribe.population,
                'male_count': tribe.male_count,
                'female_count': tribe.female_count
            }
            for tid, tribe in self.state.tribes.items()
        }
        
        # 记录本月事件
        monthly_events = {
            'month': current_month,
            'births': {k: 0 for k in self.state.tribes.keys()},
            'births_male': {k: 0 for k in self.state.tribes.keys()},
            'births_female': {k: 0 for k in self.state.tribes.keys()},
            'deaths': {k: 0 for k in self.state.tribes.keys()},
            'deaths_male': {k: 0 for k in self.state.tribes.keys()},
            'deaths_female': {k: 0 for k in self.state.tribes.keys()},
            'birth_rates': {},
            'death_rates': {},
            'selection_metrics': {},
            'shared_k': 0.0,
            'injured': {k: 0 for k in self.state.tribes.keys()},
            'competitions': []
        }

        # 每月计算共享承载力（S曲线K）
        shared_k = self._calculate_shared_k()
        monthly_events['shared_k'] = float(shared_k)
        total_population = sum(t.population for t in self.state.tribes.values())
        
        # 1. 活动分配
        for tribe in self.state.tribes.values():
            self.activity_mechanism.apply(tribe)
        
        # 2. 资源生产
        for tribe in self.state.tribes.values():
            self.production_mechanism.apply(tribe)
        
        # 3. 资源分配
        for tribe in self.state.tribes.values():
            self.distribution_mechanism.apply(tribe)

        # 3.5 表现型可塑（后天训练）
        for tribe in self.state.tribes.values():
            self.adaptation_mechanism.apply(tribe)
        
        # 4. 繁殖
        reproduction_stats_by_tribe = {}
        for tribe in self.state.tribes.values():
            newborns, self.state.individual_id_counter, reproduction_stats = \
                self.reproduction_mechanism.apply(
                    tribe,
                    self.state.individual_id_counter,
                    list(self.state.tribes.values()),
                    shared_k=shared_k,
                    total_population=total_population
                )
            reproduction_stats_by_tribe[tribe.id] = reproduction_stats
            for newborn in newborns:
                tribe.add_individual(newborn)
            monthly_events['births'][tribe.id] = len(newborns)
            monthly_events['births_male'][tribe.id] = sum(1 for n in newborns if n.gender == Gender.MALE)
            monthly_events['births_female'][tribe.id] = sum(1 for n in newborns if n.gender == Gender.FEMALE)
        
        # 5. 老化
        for tribe in self.state.tribes.values():
            self.aging_mechanism.apply(tribe)
        
        # 6. 死亡
        for tribe in self.state.tribes.values():
            deceased = self.mortality_mechanism.apply(tribe)
            monthly_events['deaths'][tribe.id] = len(deceased)
            monthly_events['deaths_male'][tribe.id] = sum(1 for d in deceased if d.gender == Gender.MALE)
            monthly_events['deaths_female'][tribe.id] = sum(1 for d in deceased if d.gender == Gender.FEMALE)
            monthly_events['injured'][tribe.id] = tribe.injured_count

        # 6.5 承载力超载死亡
        overcrowd_ratio = max(0.0, (total_population - shared_k) / max(1.0, shared_k))
        for tribe in self.state.tribes.values():
            crowded_deaths = self.mortality_mechanism.apply_crowding_pressure(
                tribe,
                overcrowd_ratio
            )
            if crowded_deaths:
                monthly_events['deaths'][tribe.id] += len(crowded_deaths)
                monthly_events['deaths_male'][tribe.id] += sum(1 for d in crowded_deaths if d.gender == Gender.MALE)
                monthly_events['deaths_female'][tribe.id] += sum(1 for d in crowded_deaths if d.gender == Gender.FEMALE)

        # 7. 部落间竞争（每3个月一次）
        if current_month % 3 == 0:
            current_k = self._calculate_dynamic_k()
            competition_results = self.competition_mechanism.apply(
                list(self.state.tribes.values()), current_k
            )
            monthly_events['competitions'] = list(competition_results.values())
            # 战争伤亡同步计入月度统计
            for (tid1, tid2), res in competition_results.items():
                monthly_events['deaths'][tid1] += res.get('tribe1_deaths', 0)
                monthly_events['deaths'][tid2] += res.get('tribe2_deaths', 0)
                monthly_events['deaths_male'][tid1] += res.get('tribe1_male_deaths', 0)
                monthly_events['deaths_female'][tid1] += res.get('tribe1_female_deaths', 0)
                monthly_events['deaths_male'][tid2] += res.get('tribe2_male_deaths', 0)
                monthly_events['deaths_female'][tid2] += res.get('tribe2_female_deaths', 0)
                monthly_events['injured'][tid1] += res.get('tribe1_injuries', 0)
                monthly_events['injured'][tid2] += res.get('tribe2_injuries', 0)

        # 7.8 低外敌压力下的大部落分裂
        self._apply_tribe_splitting()

        # 7.5 计算出生率/死亡率（总人口与分性别，含战争伤亡）
        for tid, start in month_start.items():
            start_pop = max(1, start['population'])
            start_male = max(1, start['male_count'])
            start_female = max(1, start['female_count'])

            monthly_events['birth_rates'][tid] = {
                'total': monthly_events['births'][tid] / start_pop,
                'male': monthly_events['births_male'][tid] / start_male,
                'female': monthly_events['births_female'][tid] / start_female
            }
            monthly_events['death_rates'][tid] = {
                'total': monthly_events['deaths'][tid] / start_pop,
                'male': monthly_events['deaths_male'][tid] / start_male,
                'female': monthly_events['deaths_female'][tid] / start_female
            }

        # 7.6 三阶段选择指标（配偶选择 -> 受孕出生 -> 子代存活代理）
        for tid, tribe in self.state.tribes.items():
            monthly_events['selection_metrics'][tid] = self._build_selection_metrics(
                tribe,
                reproduction_stats_by_tribe.get(tid, {})
            )
        
        # 8. 记录历史
        for tribe in self.state.tribes.values():
            tribe.record_history()
        
        # 记录本月统计
        snapshot = self._create_snapshot()
        snapshot.update(monthly_events)
        self.state.history.append(snapshot)
        
        # 检查是否需要保存检查点
        if current_month % self.config.checkpoint_interval == 0:
            self.save_checkpoint()
        
        self._emit_event('step_completed', monthly_events)
        
        return monthly_events

    def _build_selection_metrics(self, tribe: Tribe, reproduction_stats: Dict) -> Dict:
        """构建三阶段选择指标，尽量少先验地回放选择结果"""
        eligible = float(reproduction_stats.get('eligible_males_count', 0))
        choice_events = float(reproduction_stats.get('female_choice_events', 0))
        selected_unique = float(reproduction_stats.get('selected_males_count', 0))
        conception_events = float(reproduction_stats.get('conception_events', 0))

        # 子代存活代理：过去5岁队列中存活占比 + 父代特征与子代存活率相关性
        child_pool = [ind for ind in tribe.individuals.values() if ind.age <= 5]
        alive_children = [ind for ind in child_pool if ind.is_alive]
        child_survival_5y = (len(alive_children) / len(child_pool)) if child_pool else 0.0

        father_samples = []
        for ind in tribe.individuals.values():
            if ind.gender != Gender.MALE or len(ind.children) == 0:
                continue
            kids = [tribe.individuals[cid] for cid in ind.children if cid in tribe.individuals]
            if not kids:
                continue
            alive_ratio = sum(1 for k in kids if k.is_alive) / len(kids)
            father_samples.append({
                'resource': float(ind.resources),
                'effective_strength': float(ind.effective_strength),
                'effective_intelligence': float(ind.effective_intelligence),
                'effective_communication': float(ind.effective_communication),
                'alive_ratio': float(alive_ratio)
            })

        corr = {
            'resource': 0.0,
            'effective_strength': 0.0,
            'effective_intelligence': 0.0,
            'effective_communication': 0.0
        }
        if len(father_samples) >= 3:
            y = np.array([s['alive_ratio'] for s in father_samples], dtype=float)
            if float(np.std(y)) > 1e-9:
                for k in corr.keys():
                    x = np.array([s[k] for s in father_samples], dtype=float)
                    corr[k] = float(np.corrcoef(x, y)[0, 1]) if float(np.std(x)) > 1e-9 else 0.0

        return {
            'mating_stage': {
                'eligible_males': int(eligible),
                'female_choice_events': int(choice_events),
                'selected_unique_males': int(selected_unique),
                'selected_unique_rate': (selected_unique / eligible) if eligible > 0 else 0.0,
                'mate_selection_differential': reproduction_stats.get('mate_selection_differential', {})
            },
            'birth_stage': {
                'conception_events': int(conception_events),
                'conception_per_choice': (conception_events / choice_events) if choice_events > 0 else 0.0,
                'birth_selection_differential': reproduction_stats.get('birth_selection_differential', {})
            },
            'offspring_survival_stage': {
                'child_survival_5y': float(child_survival_5y),
                'father_trait_alive_child_corr': corr
            }
        }
    
    def run(self, months: Optional[int] = None) -> SimulationState:
        """运行模拟"""
        if months is None:
            months = self.config.max_simulation_months
        
        print(f"开始模拟，目标: {months} 个月")
        
        while self.state.month < months:
            events = self.step()
            
            # 检查灭绝
            extinct = [tid for tid, tribe in self.state.tribes.items() if tribe.population <= 0]
            if extinct:
                self._emit_event('extinction', {'tribes': extinct})
                for tid in extinct:
                    if tid in self.state.tribes:
                        tribe = self.state.tribes[tid]
                        print(f"部落 {tid} 已灭绝")
                        del self.state.tribes[tid]
            
            # 进度报告
            if self.state.month % 100 == 0:
                self._print_progress()
        
        print(f"模拟完成，共 {self.state.month} 个月")
        self._print_final_stats()
        
        return self.state
    
    def _calculate_dynamic_k(self) -> float:
        """计算动态环境承载力"""
        # 竞争机制也使用共享K
        return self._calculate_shared_k()

    def _calculate_shared_k(self) -> float:
        """
        共享承载力K：
        - 以食物可供养人数为主（环境承载力核心）
        - 生产力作为修正（提高持续获取食物能力）
        - 使用上下限避免数值发散
        """
        base_total_k = self.config.base_k * max(1, self.initial_tribe_count)
        total_resources = sum(t.total_resources for t in self.state.tribes.values())
        total_productivity = sum(t.productive_capacity for t in self.state.tribes.values())

        # 每人每月最低资源需求（与分配机制保持一致）
        per_capita_need = max(0.1, getattr(self.distribution_mechanism, 'base_consumption', 1.0))

        # 食物决定可供养人口规模
        k_from_food = total_resources / per_capita_need

        # 生产力提升“可持续获取资源”能力（修正项）
        tribe_n = max(1, self.initial_tribe_count)
        productivity_multiplier = 1 + min(0.35, total_productivity / (450 * tribe_n))

        raw_k = k_from_food * productivity_multiplier

        # 约束范围：下限避免极端崩盘，上限避免无限膨胀
        lower = base_total_k * 0.45
        upper = base_total_k * 1.4
        return float(min(upper, max(lower, raw_k)))

    def _has_peer_rival_for_population(self, population: int, opponent_populations: List[int]) -> bool:
        """按人口判断是否存在同等级对手"""
        if population <= 0:
            return False
        for op in opponent_populations:
            if op <= 0:
                continue
            ratio = op / max(1e-6, population)
            if self.config.split_peer_population_ratio_low <= ratio <= self.config.split_peer_population_ratio_high:
                return True
        return False

    def _split_probability(self, population: int) -> float:
        """
        分裂概率：
        - <= 阈值：0
        - >= full_population：1
        - 中间线性上升
        """
        start = self.config.split_population_threshold
        full = max(start + 1, self.config.split_probability_full_population)
        if population <= start:
            return 0.0
        if population >= full:
            return 1.0
        return (population - start) / (full - start)

    def _sample_split_fraction(self) -> float:
        """
        分裂比例：以均分0.5为均值的高斯分布。
        """
        frac = float(np.random.normal(0.5, self.config.split_ratio_sigma))
        return min(0.8, max(0.2, frac))

    def _apply_tribe_splitting(self):
        """
        大部落分裂规则：
        - 人口超过阈值后按概率触发，至1000时概率=1
        - 分裂比例服从以均分为均值的高斯分布
        - 判断“低外敌压力”在分裂后进行
        - 保证新部落不比对手低太多人口
        """
        if not self.state.tribes:
            return

        next_tid = self.state.next_tribe_id
        new_tribes = {}

        for tribe in list(self.state.tribes.values()):
            pop = tribe.population
            if pop <= self.config.split_population_threshold:
                continue

            # 超过阈值后按概率触发，人数越大概率越高
            if np.random.random() > self._split_probability(pop):
                continue

            alive = [ind for ind in tribe.individuals.values() if ind.is_alive]
            if len(alive) < 2:
                continue

            # 按高斯分布采样分裂规模（均值为均分）
            split_fraction = self._sample_split_fraction()
            split_size = int(len(alive) * split_fraction)
            split_size = max(1, min(len(alive) - 1, split_size))
            parent_after = len(alive) - split_size
            child_after = split_size

            # 分裂后条件判断（只看“外敌”，不把分裂出的兄弟部落算作对手）
            opponent_pops = [
                t.population for t in self.state.tribes.values()
                if t.id != tribe.id and t.population > 0
            ]

            # 分裂后不应出现同等级外敌
            if self._has_peer_rival_for_population(parent_after, opponent_pops):
                continue
            if self._has_peer_rival_for_population(child_after, opponent_pops):
                continue

            # 新部落不能比对手低很多（与最强对手比较）
            if opponent_pops:
                strongest_op = max(opponent_pops)
                if child_after < strongest_op * self.config.split_min_child_vs_opponent_ratio:
                    continue

            np.random.shuffle(alive)
            migrants = alive[:split_size]

            new_tribe = Tribe(id=next_tid, strength_relation=GenderStrengthRelation.EQUAL)
            for m in migrants:
                new_tribe.add_individual(m)
                if m.id in tribe.individuals:
                    del tribe.individuals[m.id]

            # 资源对半分
            transfer_meat = tribe.food_meat * 0.5
            transfer_plant = tribe.food_plant * 0.5
            tribe.food_meat -= transfer_meat
            tribe.food_plant -= transfer_plant
            tribe.total_resources = tribe.food_meat + tribe.food_plant

            new_tribe.food_meat = transfer_meat
            new_tribe.food_plant = transfer_plant
            new_tribe.total_resources = transfer_meat + transfer_plant

            new_tribes[next_tid] = new_tribe
            next_tid += 1

        self.state.tribes.update(new_tribes)
        self.state.next_tribe_id = next_tid
    
    def _create_snapshot(self) -> Dict:
        """创建当前状态快照"""
        snapshot = {
            'month': self.state.month,
            'tribes': {}
        }
        
        for tid, tribe in self.state.tribes.items():
            snapshot['tribes'][tid] = {
                'population': tribe.population,
                'male_count': tribe.male_count,
                'female_count': tribe.female_count,
                'avg_male_strength': tribe.avg_male_strength,  # 后天表现型均值（含表达）
                'avg_female_strength': tribe.avg_female_strength,
                'median_male_strength': tribe.median_male_strength,
                'median_female_strength': tribe.median_female_strength,
                'avg_male_innate_strength': tribe.avg_male_innate_strength,
                'avg_female_innate_strength': tribe.avg_female_innate_strength,
                'avg_male_strength_expression': tribe.avg_male_strength_expression,
                'avg_female_strength_expression': tribe.avg_female_strength_expression,
                'median_male_innate_strength': tribe.median_male_innate_strength,
                'median_female_innate_strength': tribe.median_female_innate_strength,
                'female_mate_preference_ratios': tribe.female_mate_preference_ratios,
                'dominant_female_mate_preference': tribe.dominant_female_mate_preference,
                'injured_count': tribe.injured_count,
                'hunters': len(tribe.hunters),
                'gatherers': len(tribe.gatherers),
                'resources': tribe.total_resources,
                'food_meat': tribe.food_meat,
                'productive_capacity': tribe.productive_capacity,
                'violence_capacity': tribe.violence_capacity
            }
        
        return snapshot
    
    def _print_progress(self):
        """打印进度"""
        print(f"\n--- 月份 {self.state.month} ---")
        for tid, tribe in self.state.tribes.items():
            print(
                f"部落 {tid}: 人口={tribe.population}, "
                f"雄均力(后天/先天)={tribe.avg_male_strength:.3f}/{tribe.avg_male_innate_strength:.3f}, "
                f"雌均力(后天/先天)={tribe.avg_female_strength:.3f}/{tribe.avg_female_innate_strength:.3f}, "
                f"力表达(雄/雌)={tribe.avg_male_strength_expression:.3f}/{tribe.avg_female_strength_expression:.3f}, "
                f"雌择偶偏好主导={tribe.dominant_female_mate_preference}, "
                f"受伤={tribe.injured_count}, 资源={tribe.total_resources:.1f}"
            )
    
    def _print_final_stats(self):
        """打印最终统计"""
        print("\n=== 最终统计 ===")
        for tid, tribe in self.state.tribes.items():
            print(f"部落 {tid}:")
            print(f"  当前人口: {tribe.population}")
            print(f"  总出生: {tribe.birth_count}")
            print(f"  总死亡: {tribe.death_count}")
            print(f"  受伤人数: {tribe.injured_count}")
            print(f"  雄性力量(后天含表达 均值/中位数): {tribe.avg_male_strength:.3f}/{tribe.median_male_strength:.3f}")
            print(f"  雌性力量(后天含表达 均值/中位数): {tribe.avg_female_strength:.3f}/{tribe.median_female_strength:.3f}")
            print(f"  雄性力量(先天均值/中位数): {tribe.avg_male_innate_strength:.3f}/{tribe.median_male_innate_strength:.3f}")
            print(f"  雌性力量(先天均值/中位数): {tribe.avg_female_innate_strength:.3f}/{tribe.median_female_innate_strength:.3f}")
            print(f"  力量表达系数(雄/雌): {tribe.avg_male_strength_expression:.3f}/{tribe.avg_female_strength_expression:.3f}")
            pref = tribe.female_mate_preference_ratios
            print(
                "  雌性择偶偏好占比(资/力/智/沟/均衡): "
                f"{pref['resource']:.2f}/{pref['strength']:.2f}/{pref['intelligence']:.2f}/"
                f"{pref['communication']:.2f}/{pref['balanced']:.2f}"
            )
            print(f"  存活率: {tribe.population / max(1, tribe.birth_count + tribe.population) * 100:.1f}%")
    
    def save_checkpoint(self, filename: Optional[str] = None):
        """保存检查点"""
        if filename is None:
            filename = f"checkpoint_month_{self.state.month}.pkl"
        
        filepath = os.path.join(self.config.checkpoint_dir, filename)
        os.makedirs(self.config.checkpoint_dir, exist_ok=True)
        
        with open(filepath, 'wb') as f:
            pickle.dump(self.state, f)
        
        print(f"检查点已保存: {filepath}")
    
    def load_checkpoint(self, filepath: str) -> bool:
        """加载检查点"""
        if not os.path.exists(filepath):
            print(f"检查点不存在: {filepath}")
            return False
        
        with open(filepath, 'rb') as f:
            self.state = pickle.load(f)
        if not hasattr(self.state, 'next_tribe_id'):
            self.state.next_tribe_id = (max(self.state.tribes.keys()) + 1) if self.state.tribes else 0
        if self.initial_tribe_count <= 0:
            self.initial_tribe_count = max(1, len(self.state.tribes))
        
        print(f"检查点已加载: {filepath}, 月份: {self.state.month}")
        self._resolve_dependencies()  # 重新解析可能更新的依赖
        return True
    
    def register_event_callback(self, callback: Callable[[str, Dict], None]):
        """注册事件回调"""
        self.event_callbacks.append(callback)
    
    def _emit_event(self, event_type: str, data: Dict):
        """触发事件"""
        for callback in self.event_callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                print(f"事件回调错误: {e}")
    
    def get_results(self) -> Dict:
        """获取模拟结果"""
        def _avg_rate(rate_key: str, tid: int, field: str) -> float:
            values = []
            for h in self.state.history:
                rate_map = h.get(rate_key, {})
                if tid in rate_map:
                    values.append(rate_map[tid].get(field, 0.0))
            return float(np.mean(values)) if values else 0.0

        def _avg_selection_metric(tid: int, stage: str, metric_key: str) -> float:
            values = []
            for h in self.state.history:
                stage_map = h.get('selection_metrics', {}).get(tid, {}).get(stage, {})
                if metric_key in stage_map:
                    values.append(stage_map[metric_key])
            return float(np.mean(values)) if values else 0.0

        return {
            'final_month': self.state.month,
            'population_structure': self.config.population_structure,
            'tribes': {
                tid: {
                    'final_population': tribe.population,
                    'birth_count': tribe.birth_count,
                    'death_count': tribe.death_count,
                    'injured_count': tribe.injured_count,
                    'avg_male_strength': tribe.avg_male_strength,
                    'avg_female_strength': tribe.avg_female_strength,
                    'median_male_strength': tribe.median_male_strength,
                    'median_female_strength': tribe.median_female_strength,
                    'avg_male_innate_strength': tribe.avg_male_innate_strength,
                    'avg_female_innate_strength': tribe.avg_female_innate_strength,
                    'avg_male_strength_expression': tribe.avg_male_strength_expression,
                    'avg_female_strength_expression': tribe.avg_female_strength_expression,
                    'median_male_innate_strength': tribe.median_male_innate_strength,
                    'median_female_innate_strength': tribe.median_female_innate_strength,
                    'female_mate_preference_ratios': tribe.female_mate_preference_ratios,
                    'dominant_female_mate_preference': tribe.dominant_female_mate_preference,
                    'avg_birth_rate_total': _avg_rate('birth_rates', tid, 'total'),
                    'avg_birth_rate_male': _avg_rate('birth_rates', tid, 'male'),
                    'avg_birth_rate_female': _avg_rate('birth_rates', tid, 'female'),
                    'avg_death_rate_total': _avg_rate('death_rates', tid, 'total'),
                    'avg_death_rate_male': _avg_rate('death_rates', tid, 'male'),
                    'avg_death_rate_female': _avg_rate('death_rates', tid, 'female'),
                    'avg_selected_unique_male_rate': _avg_selection_metric(tid, 'mating_stage', 'selected_unique_rate'),
                    'avg_conception_per_choice': _avg_selection_metric(tid, 'birth_stage', 'conception_per_choice'),
                    'avg_child_survival_5y': _avg_selection_metric(tid, 'offspring_survival_stage', 'child_survival_5y'),
                    'population_history': tribe.population_history,
                    'resource_history': tribe.resource_history
                }
                for tid, tribe in self.state.tribes.items()
            },
            'history': self.state.history
        }
