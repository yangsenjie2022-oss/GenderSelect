"""
进化机制 - 可插拔的模拟规则
所有机制都通过依赖注入配置
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional
import numpy as np
from .models import Individual, Tribe, Gender, ActivityType
from .occupations import (
    BaseOccupationPolicy,
    HuntingOccupationPolicy,
    CraftingOccupationPolicy,
    OccupationDecisionContext
)
from .reproduction import (
    ConceptionPolicy,
    InheritancePolicy,
    MatePoolProvider,
    MateSelectionConfig,
    MutationConfig,
    ParentResolver,
    PregnancyPolicy,
    ReproductionContext,
    ReproductionPipeline,
    SelectionStatsBuilder,
    WeightedMateSelectionPolicy,
)


class BaseMechanism(ABC):
    """机制基类"""

    @staticmethod
    def _month_fraction(time_step_days: Optional[float] = None, days_per_month: int = 30) -> float:
        if time_step_days is None:
            return 1.0
        return max(0.0, float(time_step_days) / max(1, int(days_per_month)))

    @staticmethod
    def _scale_probability(monthly_probability: float, month_fraction: float) -> float:
        prob = min(0.999999, max(0.0, float(monthly_probability)))
        if month_fraction >= 0.999999:
            return prob
        return 1.0 - ((1.0 - prob) ** max(0.0, month_fraction))
    
    @abstractmethod
    def apply(self, *args, **kwargs):
        """应用机制"""
        pass


class ActivityAssignmentMechanism(BaseMechanism):
    """活动分配机制 - 决定谁狩猎谁采集"""
    
    def __init__(self, 
                 hunting_risk: float = 0.15,
                 min_hunter_strength: float = 0.8,
                 min_hunter_intelligence: float = 0.9,
                 protect_fertile_female: bool = True,
                 hunter_ratio: float = 0.3,
                 enable_crafting: bool = False,
                 crafter_ratio: float = 0.08,
                 min_crafter_intelligence: float = 0.95,
                 hunt_min_age: int = 16,
                 hunt_max_age: int = 45,
                 menstrual_hunt_avoidance_rate: float = 0.85,
                 days_per_month: int = 30,
                 menstrual_low_eff_days: int = 5,
                 pregnancy_no_hunt_from_month: int = 1,
                 occupation_policies: Optional[List[BaseOccupationPolicy]] = None):
        self.hunting_risk = hunting_risk
        self.min_hunter_strength = min_hunter_strength
        self.min_hunter_intelligence = min_hunter_intelligence
        self.protect_fertile_female = protect_fertile_female
        self.hunter_ratio = hunter_ratio
        self.enable_crafting = enable_crafting
        self.crafter_ratio = crafter_ratio
        self.min_crafter_intelligence = min_crafter_intelligence
        self.hunt_min_age = hunt_min_age
        self.hunt_max_age = hunt_max_age
        self.menstrual_hunt_avoidance_rate = menstrual_hunt_avoidance_rate
        self.days_per_month = days_per_month
        self.menstrual_low_eff_days = menstrual_low_eff_days
        self.pregnancy_no_hunt_from_month = pregnancy_no_hunt_from_month
        self.occupation_policies = occupation_policies or []
        self._bootstrap_default_policies()

    def _bootstrap_default_policies(self) -> None:
        """默认装配职业策略（可被外部策略列表替换）"""
        if self.occupation_policies:
            return
        self.occupation_policies = [
            HuntingOccupationPolicy(
                hunter_ratio=self.hunter_ratio,
                min_hunter_strength=self.min_hunter_strength,
                min_hunter_intelligence=self.min_hunter_intelligence,
                hunt_min_age=self.hunt_min_age,
                hunt_max_age=self.hunt_max_age,
                protect_fertile_female=self.protect_fertile_female,
                menstrual_hunt_avoidance_rate=self.menstrual_hunt_avoidance_rate,
                days_per_month=self.days_per_month,
                menstrual_low_eff_days=self.menstrual_low_eff_days,
                pregnancy_no_hunt_from_month=self.pregnancy_no_hunt_from_month
            ),
            CraftingOccupationPolicy(
                enable_crafting=self.enable_crafting,
                crafter_ratio=self.crafter_ratio,
                min_crafter_intelligence=self.min_crafter_intelligence
            )
        ]

    def _sync_policies_from_attrs(self) -> None:
        """
        将机制参数同步到默认策略。
        这样运行时 `set activity.xxx` 后，本月即可生效。
        """
        for policy in self.occupation_policies:
            if isinstance(policy, HuntingOccupationPolicy):
                policy._ratio = self.hunter_ratio
                policy.min_hunter_strength = self.min_hunter_strength
                policy.min_hunter_intelligence = self.min_hunter_intelligence
                policy.hunt_min_age = self.hunt_min_age
                policy.hunt_max_age = self.hunt_max_age
                policy.protect_fertile_female = self.protect_fertile_female
                policy.menstrual_hunt_avoidance_rate = self.menstrual_hunt_avoidance_rate
                policy.days_per_month = self.days_per_month
                policy.menstrual_low_eff_days = self.menstrual_low_eff_days
                policy.pregnancy_no_hunt_from_month = self.pregnancy_no_hunt_from_month
            elif isinstance(policy, CraftingOccupationPolicy):
                policy.enable_crafting = self.enable_crafting
                policy._ratio = self.crafter_ratio
                policy.min_crafter_intelligence = self.min_crafter_intelligence
    
    def apply(self, tribe: Tribe) -> None:
        """为部落成员分配活动"""
        alive = [ind for ind in tribe.individuals.values() if ind.is_alive]
        if not alive:
            return

        # 运行时参数热更新后同步策略
        self._sync_policies_from_attrs()

        # 统一重置当月状态标记（供后续风险计算使用）
        for ind in alive:
            if hasattr(ind, 'menstruation_active'):
                ind.menstruation_active = False
            else:
                ind.menstruation_active = False

        context = OccupationDecisionContext(alive_population=len(alive))
        assigned_ids = set()
        crafter_ids = set()
        hunter_ids = set()
        for policy in self.occupation_policies:
            selected = policy.select(alive, assigned_ids, tribe, context)
            if not selected:
                continue
            ids = {i.id for i in selected}
            assigned_ids.update(ids)
            if policy.activity_type == ActivityType.HUNTING:
                hunter_ids = ids
            elif policy.activity_type == ActivityType.CRAFTING:
                crafter_ids = ids

        for ind in alive:
            if ind.id in hunter_ids:
                ind.assigned_activity = ActivityType.HUNTING
            elif ind.id in crafter_ids:
                ind.assigned_activity = ActivityType.CRAFTING
            else:
                ind.assigned_activity = ActivityType.GATHERING


class ResourceProductionMechanism(BaseMechanism):
    """资源生产机制"""
    
    def __init__(self,
                 meat_protein_content: float = 0.8,      # 肉类蛋白质含量
                 plant_protein_content: float = 0.2,     # 植物蛋白质含量
                 hunting_base_yield: float = 10.0,
                 gathering_base_yield: float = 6.0,
                 tool_material_gather_base: float = 0.25,
                 tool_crafting_efficiency: float = 0.9,
                 tool_hunting_bonus_max: float = 0.2,
                 tool_gathering_bonus_max: float = 0.12,
                 tool_decay_rate: float = 0.03,
                 tool_use_per_hunter: float = 0.035,
                 tool_use_per_gatherer: float = 0.015,
                 spoilage_rate: float = 0.03,
                 days_per_month: int = 30,
                 menstrual_low_eff_days: int = 5,
                 menstrual_efficiency: float = 0.85,
                 gestation_months: int = 9,
                 pregnancy_no_work_month: int = 8,
                 specialization_hunting_bonus: float = 0.08,
                 specialization_gathering_bonus: float = 0.08,
                 specialization_cap: float = 1.8):
        self.meat_protein_content = meat_protein_content
        self.plant_protein_content = plant_protein_content
        self.hunting_base_yield = hunting_base_yield
        self.gathering_base_yield = gathering_base_yield
        self.tool_material_gather_base = tool_material_gather_base
        self.tool_crafting_efficiency = tool_crafting_efficiency
        self.tool_hunting_bonus_max = tool_hunting_bonus_max
        self.tool_gathering_bonus_max = tool_gathering_bonus_max
        self.tool_decay_rate = tool_decay_rate
        self.tool_use_per_hunter = tool_use_per_hunter
        self.tool_use_per_gatherer = tool_use_per_gatherer
        self.spoilage_rate = spoilage_rate
        self.days_per_month = days_per_month
        self.menstrual_low_eff_days = menstrual_low_eff_days
        self.menstrual_efficiency = menstrual_efficiency
        self.gestation_months = gestation_months
        self.pregnancy_no_work_month = pregnancy_no_work_month
        self.specialization_hunting_bonus = specialization_hunting_bonus
        self.specialization_gathering_bonus = specialization_gathering_bonus
        self.specialization_cap = specialization_cap

    def _female_cycle_factor(self, individual: Individual) -> float:
        """
        月步长下的日级近似：
        - 未怀孕雌性：每月若干天生产力下降
        - 怀孕雌性：孕期逐月下降，最后一个月不可工作
        """
        if individual.gender != Gender.FEMALE:
            return 1.0

        # 怀孕阶段：逐月下降，孕晚期更早进入无法工作
        if individual.is_pregnant:
            if individual.pregnancy_months >= self.pregnancy_no_work_month:
                return 0.0
            # month=1 时接近 1，逐步下降到临近分娩前明显变低
            progress = individual.pregnancy_months / max(1, self.pregnancy_no_work_month - 1)
            return max(0.15, 1.0 - 0.8 * progress)

        # 未怀孕：经期低效率折算为月平均效率
        low_days = min(self.days_per_month, max(0, self.menstrual_low_eff_days))
        normal_days = max(0, self.days_per_month - low_days)
        return (normal_days + low_days * self.menstrual_efficiency) / max(1, self.days_per_month)
    
    def apply(
        self,
        tribe: Tribe,
        time_step_days: Optional[float] = None,
        days_per_month: int = 30
    ) -> Tuple[float, float]:
        """
        计算并分配资源
        返回: (meat_yield, plant_yield)
        """
        month_fraction = self._month_fraction(time_step_days, days_per_month)
        hunters = tribe.hunters
        gatherers = tribe.gatherers
        crafters = tribe.crafters

        # 资源腐败/损耗，避免无限囤积导致人口不现实爆炸
        meat_spoilage = self._scale_probability(self.spoilage_rate * 1.5, month_fraction)
        plant_spoilage = self._scale_probability(self.spoilage_rate, month_fraction)
        tool_decay = self._scale_probability(self.tool_decay_rate, month_fraction)
        tribe.food_meat = max(0.0, tribe.food_meat * (1 - meat_spoilage))
        tribe.food_plant = max(0.0, tribe.food_plant * (1 - plant_spoilage))
        tribe.stone_tools = max(0.0, tribe.stone_tools * (1 - tool_decay))

        # 工具覆盖率：石器越充足，狩猎/采集效率越高
        worker_count = max(1, len(hunters) + len(gatherers))
        tool_coverage = min(1.0, tribe.stone_tools / worker_count)
        hunting_tool_bonus = 1.0 + self.tool_hunting_bonus_max * tool_coverage
        gathering_tool_bonus = 1.0 + self.tool_gathering_bonus_max * tool_coverage
        
        # 狩猎产出（体力+智力+沟通）
        meat_yield = 0
        for hunter in hunters:
            phys_factor = self._female_cycle_factor(hunter)
            specialization = min(
                self.specialization_cap,
                1.0 + hunter.get_skill(ActivityType.HUNTING) * self.specialization_hunting_bonus
            )
            efficiency = (hunter.effective_strength * 0.4 +
                         hunter.effective_intelligence * 0.4 +
                         hunter.effective_communication * 0.2) * hunter.work_efficiency * phys_factor * specialization * hunting_tool_bonus
            # 团队协作加成
            team_bonus = 1 + (len(hunters) - 1) * 0.05
            meat_yield += self.hunting_base_yield * month_fraction * efficiency * team_bonus
        
        # 采集产出（稳定但较低）
        plant_yield = 0
        tool_material_yield = 0.0
        for gatherer in gatherers:
            phys_factor = self._female_cycle_factor(gatherer)
            specialization = min(
                self.specialization_cap,
                1.0 + gatherer.get_skill(ActivityType.GATHERING) * self.specialization_gathering_bonus
            )
            efficiency = (
                gatherer.effective_intelligence * 0.3 + gatherer.effective_strength * 0.2 + 0.5
            ) * gatherer.work_efficiency * phys_factor * specialization * gathering_tool_bonus
            plant_yield += self.gathering_base_yield * month_fraction * efficiency
            # 采集时顺带获取少量石料等工具原料
            tool_material_yield += (
                self.tool_material_gather_base
                * month_fraction
                * (0.6 + 0.4 * gatherer.work_efficiency)
            )

        tribe.tool_material = max(0.0, tribe.tool_material + tool_material_yield)

        # 工匠将原料加工为可用石器库存
        crafted_tools = 0.0
        for crafter in crafters:
            craft_eff = (
                crafter.effective_intelligence * 0.55
                + crafter.effective_communication * 0.30
                + crafter.effective_strength * 0.15
            )
            craft_specialization = min(
                self.specialization_cap,
                1.0 + crafter.get_skill(ActivityType.CRAFTING) * self.specialization_gathering_bonus
            )
            craft_amount = max(
                0.0,
                craft_eff
                * crafter.work_efficiency
                * self.tool_crafting_efficiency
                * 0.18
                * month_fraction
                * craft_specialization
            )
            material_used = min(tribe.tool_material, craft_amount)
            if material_used <= 0:
                continue
            tribe.tool_material -= material_used
            crafted_tools += material_used
        tribe.stone_tools = max(0.0, tribe.stone_tools + crafted_tools)

        # 石器使用损耗（狩猎损耗更快）
        tool_used = (
            len(hunters) * self.tool_use_per_hunter
            + len(gatherers) * self.tool_use_per_gatherer
        ) * month_fraction
        tribe.stone_tools = max(0.0, tribe.stone_tools - tool_used)
        
        # 存储到部落（确保非负）
        tribe.food_meat = max(0, tribe.food_meat + meat_yield)
        tribe.food_plant = max(0, tribe.food_plant + plant_yield)
        tribe.total_resources = tribe.food_meat + tribe.food_plant
        
        return meat_yield, plant_yield


class MortalityMechanism(BaseMechanism):
    """死亡机制"""
    
    def __init__(self,
                 base_mortality: float = 0.02,
                 hunting_mortality: float = 0.12,
                 hunting_injury: float = 0.18,
                 pregnancy_mortality: float = 0.02,
                 infant_mortality: float = 0.15,
                 old_age_start: int = 50,
                 resource_threshold: float = 0.5,
                 injury_worsen_rate: float = 0.2,
                 injury_recover_rate: float = 0.3,
                 menstrual_hunting_extra_mortality: float = 0.035,
                 menstrual_hunting_extra_injury: float = 0.06,
                 pregnancy_hunting_extra_mortality: float = 0.08,
                 pregnancy_hunting_extra_injury: float = 0.12):
        self.base_mortality = base_mortality
        self.hunting_mortality = hunting_mortality
        self.hunting_injury = hunting_injury
        self.pregnancy_mortality = pregnancy_mortality
        self.infant_mortality = infant_mortality
        self.old_age_start = old_age_start
        self.resource_threshold = resource_threshold  # 资源不足阈值
        self.injury_worsen_rate = injury_worsen_rate
        self.injury_recover_rate = injury_recover_rate
        self.menstrual_hunting_extra_mortality = menstrual_hunting_extra_mortality
        self.menstrual_hunting_extra_injury = menstrual_hunting_extra_injury
        self.pregnancy_hunting_extra_mortality = pregnancy_hunting_extra_mortality
        self.pregnancy_hunting_extra_injury = pregnancy_hunting_extra_injury
    
    def apply(
        self,
        tribe: Tribe,
        time_step_days: Optional[float] = None,
        days_per_month: int = 30
    ) -> List[Individual]:
        """应用死亡，返回死亡个体列表"""
        month_fraction = self._month_fraction(time_step_days, days_per_month)
        deceased = []
        
        for ind in list(tribe.individuals.values()):
            if not ind.is_alive:
                continue
            resource_threshold = self.resource_threshold * max(month_fraction, 1e-9)
                
            death_prob = self._scale_probability(self.base_mortality, month_fraction)
            
            # 狩猎死亡/受伤风险
            if ind.assigned_activity == ActivityType.HUNTING:
                death_prob += self._scale_probability(self.hunting_mortality, month_fraction)
                injury_prob = self._scale_probability(self.hunting_injury, month_fraction)

                # 经期狩猎：气味暴露提高风险
                if ind.gender == Gender.FEMALE and getattr(ind, 'menstruation_active', False):
                    death_prob += self._scale_probability(
                        self.menstrual_hunting_extra_mortality,
                        month_fraction
                    )
                    injury_prob += self._scale_probability(
                        self.menstrual_hunting_extra_injury,
                        month_fraction
                    )

                # 怀孕狩猎（理论上已被分工层尽量避免）：若发生，风险更高
                if ind.gender == Gender.FEMALE and ind.is_pregnant:
                    death_prob += self._scale_probability(
                        self.pregnancy_hunting_extra_mortality,
                        month_fraction
                    )
                    injury_prob += self._scale_probability(
                        self.pregnancy_hunting_extra_injury,
                        month_fraction
                    )

                if np.random.random() < injury_prob:
                    ind.injury_level = min(1.0, ind.injury_level + np.random.uniform(0.08, 0.25))
                    ind.injury_months += 1

            # 受伤状态演化：可能好转，也可能恶化
            if ind.is_injured:
                recover_bias = 0.08 if ind.resources >= resource_threshold else -0.08
                recover_prob = self._scale_probability(
                    max(0.02, self.injury_recover_rate + recover_bias),
                    month_fraction
                )
                worsen_prob = self._scale_probability(
                    max(0.02, self.injury_worsen_rate - recover_bias),
                    month_fraction
                )
                if np.random.random() < recover_prob:
                    ind.injury_level = max(0.0, ind.injury_level - np.random.uniform(0.05, 0.16))
                elif np.random.random() < worsen_prob:
                    ind.injury_level = min(1.0, ind.injury_level + np.random.uniform(0.04, 0.14))
                ind.injury_months += 1
                death_prob += self._scale_probability(ind.injury_level * 0.08, month_fraction)
            
            # 怀孕死亡风险
            if ind.is_pregnant:
                death_prob += self._scale_probability(self.pregnancy_mortality, month_fraction)
            
            # 年龄风险
            if ind.age > self.old_age_start:
                death_prob += self._scale_probability(
                    (ind.age - self.old_age_start) * 0.005,
                    month_fraction
                )
            
            # 婴儿死亡率
            if ind.age < 2:
                death_prob = self._scale_probability(self.infant_mortality, month_fraction)
            
            # 健康度影响（资源不足会降低健康）
            if ind.resources < resource_threshold:
                ind.health -= 0.05 * month_fraction
                death_prob += self._scale_probability(0.02, month_fraction)
            elif ind.health < 1.0:
                ind.health = min(1.0, ind.health + 0.01 * month_fraction)
            
            # 随机死亡判定
            if np.random.random() < death_prob or ind.health <= 0 or ind.injury_level >= 1.0:
                ind.is_alive = False
                tribe.death_count += 1
                deceased.append(ind)
        
        return deceased

    def apply_crowding_pressure(
        self,
        tribe: Tribe,
        shared_overcrowd_ratio: float,
        time_step_days: Optional[float] = None,
        days_per_month: int = 30
    ) -> List[Individual]:
        """
        承载力压力死亡：使用共享K，当总人口超过总K时各部落都承受额外死亡压力。
        """
        deceased = []
        if tribe.population <= 0 or shared_overcrowd_ratio <= 0:
            return deceased

        month_fraction = self._month_fraction(time_step_days, days_per_month)
        extra_death_prob = self._scale_probability(
            min(0.25, 0.03 + shared_overcrowd_ratio * 0.12),
            month_fraction
        )

        for ind in list(tribe.individuals.values()):
            if not ind.is_alive:
                continue
            if np.random.random() < extra_death_prob:
                ind.is_alive = False
                tribe.death_count += 1
                deceased.append(ind)
        return deceased


class ReproductionMechanism(BaseMechanism):
    """繁殖机制"""

    def __init__(self,
                 gestation_months: int = 9,
                 fertility_cycle: int = 1,
                 min_resources_for_pregnancy: float = 15.0,
                 male_competition_factor: float = 0.3,
                 cross_tribe_mating_rate: float = 0.05,
                 inheritance_mutation_std: float = 0.03,
                 preference_mutation_std: float = 0.02,
                 expression_mutation_std: float = 0.02,
                 selection_resource_factor: float = 1.0,
                 selection_strength_factor: float = 1.0,
                 selection_intelligence_factor: float = 1.0,
                 selection_communication_factor: float = 1.0,
                 random_mating_rate: float = 0.0,
                 selection_all_disabled: bool = False):
        self.gestation_months = gestation_months
        self.fertility_cycle = fertility_cycle
        self.min_resources_for_pregnancy = min_resources_for_pregnancy
        self.male_competition_factor = male_competition_factor
        self.cross_tribe_mating_rate = cross_tribe_mating_rate
        self.inheritance_mutation_std = inheritance_mutation_std
        self.preference_mutation_std = preference_mutation_std
        self.expression_mutation_std = expression_mutation_std
        # 性选择维度开关/比例（0=关闭该维度，1=默认，支持 >1 强化）
        self.selection_resource_factor = selection_resource_factor
        self.selection_strength_factor = selection_strength_factor
        self.selection_intelligence_factor = selection_intelligence_factor
        self.selection_communication_factor = selection_communication_factor
        # 全局随机择偶比例（可用于做“部分随机选择”对照）
        self.random_mating_rate = random_mating_rate
        # 一键关闭全部性选择维度（用于严格随机择偶对照）
        self.selection_all_disabled = selection_all_disabled

        self.mate_pool_provider = MatePoolProvider(
            cross_tribe_mating_rate=self.cross_tribe_mating_rate
        )
        self.mate_selection_policy = WeightedMateSelectionPolicy()
        self.conception_policy = ConceptionPolicy(
            min_resources_for_pregnancy=self.min_resources_for_pregnancy
        )
        self.inheritance_policy = InheritancePolicy()
        self.pregnancy_policy = PregnancyPolicy(
            gestation_months=self.gestation_months,
            parent_resolver=ParentResolver(),
            inheritance_policy=self.inheritance_policy
        )
        self.selection_stats_builder = SelectionStatsBuilder()
        self.reproduction_pipeline = ReproductionPipeline(
            mate_pool_provider=self.mate_pool_provider,
            mate_selection_policy=self.mate_selection_policy,
            conception_policy=self.conception_policy,
            pregnancy_policy=self.pregnancy_policy,
            stats_builder=self.selection_stats_builder
        )

    def _sync_pipeline_from_attrs(self) -> None:
        """Keep policy objects aligned with hot-updated mechanism attributes."""
        self.mate_pool_provider.cross_tribe_mating_rate = self.cross_tribe_mating_rate
        self.conception_policy.min_resources_for_pregnancy = self.min_resources_for_pregnancy
        self.pregnancy_policy.gestation_months = self.gestation_months
        self.inheritance_policy.mutations = MutationConfig(
            inheritance_mutation_std=self.inheritance_mutation_std,
            preference_mutation_std=self.preference_mutation_std,
            expression_mutation_std=self.expression_mutation_std
        )
        self.mate_selection_policy.config = MateSelectionConfig(
            male_competition_factor=self.male_competition_factor,
            selection_resource_factor=self.selection_resource_factor,
            selection_strength_factor=self.selection_strength_factor,
            selection_intelligence_factor=self.selection_intelligence_factor,
            selection_communication_factor=self.selection_communication_factor,
            random_mating_rate=self.random_mating_rate,
            selection_all_disabled=self.selection_all_disabled
        )

    def apply(
        self,
        tribe: Tribe,
        individual_id_counter: int,
        all_tribes: Optional[List[Tribe]] = None,
        shared_k: Optional[float] = None,
        total_population: Optional[int] = None,
        time_step_days: Optional[float] = None,
        days_per_month: int = 30
    ) -> Tuple[List[Individual], int, Dict]:
        """
        处理繁殖
        返回: (新生儿列表, 更新的ID计数器)
        """
        month_fraction = self._month_fraction(time_step_days, days_per_month)
        self._sync_pipeline_from_attrs()
        context = ReproductionContext(
            all_tribes=all_tribes or [tribe],
            shared_k=shared_k,
            total_population=total_population,
            month_fraction=month_fraction
        )
        result = self.reproduction_pipeline.apply(
            tribe,
            individual_id_counter,
            context
        )
        return result.newborns, result.next_individual_id, result.stats


class ResourceDistributionMechanism(BaseMechanism):
    """资源分配机制"""
    
    def __init__(self,
                 base_consumption: float = 2.0,
                 pregnancy_extra: float = 1.5,
                 hunter_bonus: float = 0.3,
                 gatherer_bonus: float = 0.0,
                 crafter_bonus: float = 0.0,
                 strength_metabolic_scale: float = 0.22,
                 child_priority: bool = True):
        self.base_consumption = base_consumption
        self.pregnancy_extra = pregnancy_extra
        self.hunter_bonus = hunter_bonus
        self.gatherer_bonus = gatherer_bonus
        self.crafter_bonus = crafter_bonus
        self.strength_metabolic_scale = strength_metabolic_scale
        self.child_priority = child_priority
    
    def apply(
        self,
        tribe: Tribe,
        time_step_days: Optional[float] = None,
        days_per_month: int = 30
    ) -> None:
        """分配资源给个体"""
        month_fraction = self._month_fraction(time_step_days, days_per_month)
        alive_individuals = [ind for ind in tribe.individuals.values() if ind.is_alive]
        
        if not alive_individuals:
            return
        
        # 总需求
        total_need = 0
        individual_needs = {}
        
        for ind in alive_individuals:
            need = self.base_consumption * month_fraction
            if ind.is_pregnant:
                need += self.pregnancy_extra * month_fraction
            if ind.assigned_activity == ActivityType.HUNTING:
                need += self.hunter_bonus * month_fraction  # 狩猎者需要更多能量
            elif ind.assigned_activity == ActivityType.GATHERING:
                need += self.gatherer_bonus * month_fraction
            elif ind.assigned_activity == ActivityType.CRAFTING:
                # 对工匠提供职业资源收益，可在性选择中通过 resources 间接体现
                need += self.crafter_bonus * month_fraction
            # 体能与体格代谢成本：不是性别惩罚，而是能力代价
            need += (
                max(0.0, ind.effective_strength - 0.9)
                * self.strength_metabolic_scale
                * month_fraction
            )
            
            individual_needs[ind.id] = need
            total_need += need
        
        # 按比例分配（不超过可用资源）
        available = max(0, tribe.total_resources)
        if total_need > 0 and available > 0:
            scale = min(1.0, available / total_need)  # 如果资源不足，按比例减少
            
            for ind in alive_individuals:
                allocated = individual_needs[ind.id] * scale
                ind.resources = allocated
                
                # 从部落扣除
                if tribe.food_meat > 0:
                    meat_taken = min(tribe.food_meat, allocated * 0.6)  # 优先吃肉
                    tribe.food_meat = max(0, tribe.food_meat - meat_taken)
                    remaining = allocated - meat_taken
                    tribe.food_plant = max(0, tribe.food_plant - min(tribe.food_plant, remaining))
                else:
                    tribe.food_plant = max(0, tribe.food_plant - min(tribe.food_plant, allocated))
        else:
            # 资源耗尽
            for ind in alive_individuals:
                ind.resources = 0
        
        tribe.total_resources = max(0, tribe.food_meat + tribe.food_plant)


class PhenotypeAdaptationMechanism(BaseMechanism):
    """表现型可塑机制：工作经验改变属性（不遗传）"""

    def __init__(
        self,
        hunting_exp_gain: float = 0.12,
        gathering_exp_gain: float = 0.12,
        cross_decay: float = 0.04,
        hunt_strength_gain: float = 0.006,
        hunt_intelligence_gain: float = 0.003,
        hunt_communication_gain: float = 0.003,
        gather_strength_gain: float = 0.002,
        gather_intelligence_gain: float = 0.006,
        gather_communication_gain: float = 0.005,
        crafting_exp_gain: float = 0.11,
        craft_strength_gain: float = 0.0025,
        craft_intelligence_gain: float = 0.0055,
        craft_communication_gain: float = 0.005,
        adaptation_cap_delta: float = 0.35,
        innate_pull_rate: float = 0.03,
        resource_penalty_threshold: float = 0.8,
        starvation_attr_penalty: float = 0.01
    ):
        self.hunting_exp_gain = hunting_exp_gain
        self.gathering_exp_gain = gathering_exp_gain
        self.cross_decay = cross_decay
        self.hunt_strength_gain = hunt_strength_gain
        self.hunt_intelligence_gain = hunt_intelligence_gain
        self.hunt_communication_gain = hunt_communication_gain
        self.gather_strength_gain = gather_strength_gain
        self.gather_intelligence_gain = gather_intelligence_gain
        self.gather_communication_gain = gather_communication_gain
        self.crafting_exp_gain = crafting_exp_gain
        self.craft_strength_gain = craft_strength_gain
        self.craft_intelligence_gain = craft_intelligence_gain
        self.craft_communication_gain = craft_communication_gain
        self.adaptation_cap_delta = adaptation_cap_delta
        self.innate_pull_rate = innate_pull_rate
        self.resource_penalty_threshold = resource_penalty_threshold
        self.starvation_attr_penalty = starvation_attr_penalty

    def _clamp_around_innate(self, ind: Individual):
        low_s = max(0.5, ind.innate_strength - self.adaptation_cap_delta)
        high_s = ind.innate_strength + self.adaptation_cap_delta
        low_i = max(0.5, ind.innate_intelligence - self.adaptation_cap_delta)
        high_i = ind.innate_intelligence + self.adaptation_cap_delta
        low_c = max(0.5, ind.innate_communication - self.adaptation_cap_delta)
        high_c = ind.innate_communication + self.adaptation_cap_delta
        ind.strength = min(high_s, max(low_s, ind.strength))
        ind.intelligence = min(high_i, max(low_i, ind.intelligence))
        ind.communication = min(high_c, max(low_c, ind.communication))

    def apply(
        self,
        tribe: Tribe,
        time_step_days: Optional[float] = None,
        days_per_month: int = 30
    ) -> None:
        month_fraction = self._month_fraction(time_step_days, days_per_month)
        innate_pull = self._scale_probability(self.innate_pull_rate, month_fraction)
        for ind in tribe.individuals.values():
            if not ind.is_alive:
                continue

            # 基于工作的经验积累与属性塑形
            if ind.assigned_activity == ActivityType.HUNTING:
                hunt_skill = ind.add_skill(ActivityType.HUNTING, self.hunting_exp_gain * month_fraction)
                ind.decay_skill(ActivityType.GATHERING, self.cross_decay * month_fraction)
                ind.decay_skill(ActivityType.CRAFTING, self.cross_decay * 0.7 * month_fraction)
                ind.strength += self.hunt_strength_gain * month_fraction * (1 + 0.05 * hunt_skill)
                ind.intelligence += self.hunt_intelligence_gain * month_fraction * (1 + 0.05 * hunt_skill)
                ind.communication += self.hunt_communication_gain * month_fraction * (1 + 0.05 * hunt_skill)
            elif ind.assigned_activity == ActivityType.GATHERING:
                gather_skill = ind.add_skill(ActivityType.GATHERING, self.gathering_exp_gain * month_fraction)
                ind.decay_skill(ActivityType.HUNTING, self.cross_decay * month_fraction)
                ind.decay_skill(ActivityType.CRAFTING, self.cross_decay * 0.5 * month_fraction)
                ind.strength += self.gather_strength_gain * month_fraction * (1 + 0.05 * gather_skill)
                ind.intelligence += self.gather_intelligence_gain * month_fraction * (1 + 0.05 * gather_skill)
                ind.communication += self.gather_communication_gain * month_fraction * (1 + 0.05 * gather_skill)
            elif ind.assigned_activity == ActivityType.CRAFTING:
                craft_skill = ind.add_skill(ActivityType.CRAFTING, self.crafting_exp_gain * month_fraction)
                ind.decay_skill(ActivityType.HUNTING, self.cross_decay * 0.6 * month_fraction)
                ind.decay_skill(ActivityType.GATHERING, self.cross_decay * 0.4 * month_fraction)
                ind.strength += self.craft_strength_gain * month_fraction * (1 + 0.05 * craft_skill)
                ind.intelligence += self.craft_intelligence_gain * month_fraction * (1 + 0.05 * craft_skill)
                ind.communication += self.craft_communication_gain * month_fraction * (1 + 0.05 * craft_skill)

            # 环境约束：资源不足时属性表现下降
            if ind.resources < self.resource_penalty_threshold:
                ind.strength = max(0.5, ind.strength - self.starvation_attr_penalty * month_fraction)
                ind.intelligence = max(0.5, ind.intelligence - self.starvation_attr_penalty * 0.6 * month_fraction)
                ind.communication = max(0.5, ind.communication - self.starvation_attr_penalty * 0.6 * month_fraction)

            # 基因基线回拉：表现型受先天约束，但可被环境塑形
            ind.strength += (ind.innate_strength - ind.strength) * innate_pull
            ind.intelligence += (ind.innate_intelligence - ind.intelligence) * innate_pull
            ind.communication += (ind.innate_communication - ind.communication) * innate_pull

            self._clamp_around_innate(ind)


class CompetitionMechanism(BaseMechanism):
    """部落间竞争机制"""
    
    def __init__(self,
                 competition_probability: float = 0.1,
                 resource_transfer_rate: float = 0.2,
                 population_pressure_factor: float = 0.5,
                 battle_casualty_scale: float = 0.06,
                 battle_injury_scale: float = 0.14):
        self.competition_probability = competition_probability
        self.resource_transfer_rate = resource_transfer_rate
        self.population_pressure_factor = population_pressure_factor
        self.battle_casualty_scale = battle_casualty_scale
        self.battle_injury_scale = battle_injury_scale

    def _apply_battle_damage(self, tribe: Tribe, casualty_rate: float, injury_rate: float) -> Dict[str, int]:
        """按战斗烈度对部落造成死亡与受伤"""
        alive = [ind for ind in tribe.individuals.values() if ind.is_alive]
        if not alive:
            return {'deaths': 0, 'injuries': 0, 'male_deaths': 0, 'female_deaths': 0}

        deaths = 0
        injuries = 0
        male_deaths = 0
        female_deaths = 0
        for ind in alive:
            # 猎人/壮年更容易卷入战斗
            exposure = 1.0
            if ind.assigned_activity == ActivityType.HUNTING:
                exposure = 1.4
            elif ind.age < 16 or ind.age > 55:
                exposure = 0.6

            if np.random.random() < min(0.6, casualty_rate * exposure):
                ind.is_alive = False
                tribe.death_count += 1
                deaths += 1
                if ind.gender == Gender.MALE:
                    male_deaths += 1
                else:
                    female_deaths += 1
                continue

            if np.random.random() < min(0.8, injury_rate * exposure):
                ind.injury_level = min(1.0, ind.injury_level + np.random.uniform(0.08, 0.3))
                ind.injury_months += 1
                injuries += 1

        return {
            'deaths': deaths,
            'injuries': injuries,
            'male_deaths': male_deaths,
            'female_deaths': female_deaths
        }
    
    def apply(self, tribes: List[Tribe], global_k: float) -> Dict[Tuple[int, int], Dict]:
        """
        处理部落间竞争
        返回竞争结果记录
        """
        results = {}
        
        for i, tribe1 in enumerate(tribes):
            for j, tribe2 in enumerate(tribes[i+1:], i+1):
                # 竞争概率与接近K值成正比
                pop_pressure1 = max(0, (tribe1.population - global_k * 0.8) / global_k)
                pop_pressure2 = max(0, (tribe2.population - global_k * 0.8) / global_k)
                
                if np.random.random() > self.competition_probability * (1 + pop_pressure1 + pop_pressure2):
                    continue
                
                # 计算战力
                power1 = tribe1.violence_capacity + tribe1.productive_capacity * 0.5
                power2 = tribe2.violence_capacity + tribe2.productive_capacity * 0.5
                
                # 随机因素
                power1 *= np.random.normal(1, 0.2)
                power2 *= np.random.normal(1, 0.2)
                
                result = {
                    'power1': power1,
                    'power2': power2,
                    'winner': None,
                    'resources_transferred': 0,
                    'tribe1_deaths': 0,
                    'tribe2_deaths': 0,
                    'tribe1_injuries': 0,
                    'tribe2_injuries': 0,
                    'tribe1_male_deaths': 0,
                    'tribe1_female_deaths': 0,
                    'tribe2_male_deaths': 0,
                    'tribe2_female_deaths': 0
                }
                
                if power1 > power2 * 1.1:  # 需要明显优势
                    # Tribe1 获胜
                    transfer = tribe2.total_resources * self.resource_transfer_rate
                    transfer_tool_material = tribe2.tool_material * self.resource_transfer_rate
                    transfer_stone_tools = tribe2.stone_tools * self.resource_transfer_rate
                    tribe1.total_resources += transfer
                    tribe2.total_resources = max(0, tribe2.total_resources - transfer)
                    tribe1.food_meat += transfer * 0.6
                    tribe2.food_meat = max(0, tribe2.food_meat - transfer * 0.6)
                    tribe1.tool_material += transfer_tool_material
                    tribe2.tool_material = max(0, tribe2.tool_material - transfer_tool_material)
                    tribe1.stone_tools += transfer_stone_tools
                    tribe2.stone_tools = max(0, tribe2.stone_tools - transfer_stone_tools)
                    result['winner'] = tribe1.id
                    result['resources_transferred'] = transfer
                    ratio = power1 / max(1e-6, power2)
                    loser_damage = self._apply_battle_damage(
                        tribe2,
                        casualty_rate=min(0.35, self.battle_casualty_scale * ratio),
                        injury_rate=min(0.55, self.battle_injury_scale * ratio)
                    )
                    winner_damage = self._apply_battle_damage(
                        tribe1,
                        casualty_rate=min(0.15, self.battle_casualty_scale * 0.35),
                        injury_rate=min(0.25, self.battle_injury_scale * 0.45)
                    )
                    result['tribe1_deaths'] = winner_damage['deaths']
                    result['tribe2_deaths'] = loser_damage['deaths']
                    result['tribe1_injuries'] = winner_damage['injuries']
                    result['tribe2_injuries'] = loser_damage['injuries']
                    result['tribe1_male_deaths'] = winner_damage['male_deaths']
                    result['tribe1_female_deaths'] = winner_damage['female_deaths']
                    result['tribe2_male_deaths'] = loser_damage['male_deaths']
                    result['tribe2_female_deaths'] = loser_damage['female_deaths']
                    
                elif power2 > power1 * 1.1:
                    # Tribe2 获胜
                    transfer = tribe1.total_resources * self.resource_transfer_rate
                    transfer_tool_material = tribe1.tool_material * self.resource_transfer_rate
                    transfer_stone_tools = tribe1.stone_tools * self.resource_transfer_rate
                    tribe2.total_resources += transfer
                    tribe1.total_resources = max(0, tribe1.total_resources - transfer)
                    tribe2.food_meat += transfer * 0.6
                    tribe1.food_meat = max(0, tribe1.food_meat - transfer * 0.6)
                    tribe2.tool_material += transfer_tool_material
                    tribe1.tool_material = max(0, tribe1.tool_material - transfer_tool_material)
                    tribe2.stone_tools += transfer_stone_tools
                    tribe1.stone_tools = max(0, tribe1.stone_tools - transfer_stone_tools)
                    result['winner'] = tribe2.id
                    result['resources_transferred'] = transfer
                    ratio = power2 / max(1e-6, power1)
                    loser_damage = self._apply_battle_damage(
                        tribe1,
                        casualty_rate=min(0.35, self.battle_casualty_scale * ratio),
                        injury_rate=min(0.55, self.battle_injury_scale * ratio)
                    )
                    winner_damage = self._apply_battle_damage(
                        tribe2,
                        casualty_rate=min(0.15, self.battle_casualty_scale * 0.35),
                        injury_rate=min(0.25, self.battle_injury_scale * 0.45)
                    )
                    result['tribe1_deaths'] = loser_damage['deaths']
                    result['tribe2_deaths'] = winner_damage['deaths']
                    result['tribe1_injuries'] = loser_damage['injuries']
                    result['tribe2_injuries'] = winner_damage['injuries']
                    result['tribe1_male_deaths'] = loser_damage['male_deaths']
                    result['tribe1_female_deaths'] = loser_damage['female_deaths']
                    result['tribe2_male_deaths'] = winner_damage['male_deaths']
                    result['tribe2_female_deaths'] = winner_damage['female_deaths']
                else:
                    # 势均力敌时双方都受损
                    damage1 = self._apply_battle_damage(
                        tribe1,
                        casualty_rate=self.battle_casualty_scale * 0.6,
                        injury_rate=self.battle_injury_scale * 0.8
                    )
                    damage2 = self._apply_battle_damage(
                        tribe2,
                        casualty_rate=self.battle_casualty_scale * 0.6,
                        injury_rate=self.battle_injury_scale * 0.8
                    )
                    result['tribe1_deaths'] = damage1['deaths']
                    result['tribe2_deaths'] = damage2['deaths']
                    result['tribe1_injuries'] = damage1['injuries']
                    result['tribe2_injuries'] = damage2['injuries']
                    result['tribe1_male_deaths'] = damage1['male_deaths']
                    result['tribe1_female_deaths'] = damage1['female_deaths']
                    result['tribe2_male_deaths'] = damage2['male_deaths']
                    result['tribe2_female_deaths'] = damage2['female_deaths']
                
                results[(tribe1.id, tribe2.id)] = result
        
        return results


class BeastAttackMechanism(BaseMechanism):
    """野兽攻击机制（外部生态风险）"""

    def __init__(
        self,
        attack_probability: float = 0.025,
        base_attack_severity: float = 0.12,
        death_scale: float = 0.02,
        injury_scale: float = 0.07,
        starvation_risk_factor: float = 0.25
    ):
        self.attack_probability = attack_probability
        self.base_attack_severity = base_attack_severity
        self.death_scale = death_scale
        self.injury_scale = injury_scale
        self.starvation_risk_factor = starvation_risk_factor

    def _defense_power(self, tribe: Tribe) -> float:
        alive = [i for i in tribe.individuals.values() if i.is_alive]
        if not alive:
            return 0.0
        avg_strength = float(np.mean([i.effective_strength for i in alive]))
        avg_comm = float(np.mean([i.effective_communication for i in alive]))
        hunter_share = len(tribe.hunters) / max(1, len(alive))
        # 组织度（沟通）+ 体力 + 狩猎参与比例共同决定防御能力
        return avg_strength * 0.45 + avg_comm * 0.40 + hunter_share * 0.15

    def _apply_attack_damage(
        self,
        tribe: Tribe,
        death_rate: float,
        injury_rate: float
    ) -> Dict[str, int]:
        alive = [i for i in tribe.individuals.values() if i.is_alive]
        if not alive:
            return {'deaths': 0, 'injuries': 0, 'male_deaths': 0, 'female_deaths': 0}

        deaths = injuries = male_deaths = female_deaths = 0
        for ind in alive:
            exposure = 1.0
            if ind.assigned_activity == ActivityType.HUNTING:
                exposure = 1.2
            elif ind.assigned_activity == ActivityType.CRAFTING:
                exposure = 0.9

            if np.random.random() < min(0.45, death_rate * exposure):
                ind.is_alive = False
                tribe.death_count += 1
                deaths += 1
                if ind.gender == Gender.MALE:
                    male_deaths += 1
                else:
                    female_deaths += 1
                continue

            if np.random.random() < min(0.7, injury_rate * exposure):
                ind.injury_level = min(1.0, ind.injury_level + np.random.uniform(0.06, 0.22))
                ind.injury_months += 1
                injuries += 1

        return {
            'deaths': deaths,
            'injuries': injuries,
            'male_deaths': male_deaths,
            'female_deaths': female_deaths
        }

    def apply(
        self,
        tribes: List[Tribe],
        shared_k: float,
        time_step_days: Optional[float] = None,
        days_per_month: int = 30
    ) -> Dict[int, Dict]:
        """
        对每个部落独立判定野兽攻击。
        返回: {tribe_id: {'attacked': bool, deaths, injuries, male_deaths, female_deaths, severity}}
        """
        results = {}
        month_fraction = self._month_fraction(time_step_days, days_per_month)
        total_pop = sum(t.population for t in tribes)
        pressure = max(0.0, (total_pop - shared_k) / max(1.0, shared_k)) if shared_k > 0 else 0.0

        for tribe in tribes:
            if tribe.population <= 0:
                continue
            # 资源紧张时野兽攻击风险略增（觅食冲突加剧）
            pop_need = max(1, tribe.population)
            per_capita_resource = tribe.total_resources / pop_need
            scarcity = max(0.0, 1.0 - per_capita_resource)
            monthly_attack = min(
                0.5,
                self.attack_probability * (1 + pressure * 0.6 + scarcity * self.starvation_risk_factor)
            )
            p_attack = self._scale_probability(monthly_attack, month_fraction)

            if np.random.random() > p_attack:
                continue

            defense = self._defense_power(tribe)
            severity = max(0.02, self.base_attack_severity * np.random.normal(1.0, 0.15))
            # 防御越强，伤亡率越低
            defense_factor = 1 / max(0.5, defense)
            death_rate = min(0.25, self.death_scale * severity * defense_factor)
            injury_rate = min(0.45, self.injury_scale * severity * defense_factor)

            damage = self._apply_attack_damage(tribe, death_rate, injury_rate)
            results[tribe.id] = {
                'attacked': True,
                'severity': float(severity),
                **damage
            }
        return results


class AgingMechanism(BaseMechanism):
    """老化机制"""
    
    def __init__(self, months_per_year: int = 12):
        self.months_per_year = months_per_year
    
    def apply(
        self,
        tribe: Tribe,
        time_step_days: Optional[float] = None,
        days_per_month: int = 30
    ) -> None:
        """增加年龄"""
        month_fraction = self._month_fraction(time_step_days, days_per_month)
        for ind in tribe.individuals.values():
            if ind.is_alive:
                ind.age += month_fraction / self.months_per_year
