"""
进化机制 - 可插拔的模拟规则
所有机制都通过依赖注入配置
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional
import numpy as np
from .models import Individual, Tribe, Gender, ActivityType, GenderStrengthRelation


class BaseMechanism(ABC):
    """机制基类"""
    
    @abstractmethod
    def apply(self, *args, **kwargs):
        """应用机制"""
        pass


class ActivityAssignmentMechanism(BaseMechanism):
    """活动分配机制 - 决定谁狩猎谁采集"""
    
    def __init__(self, 
                 hunting_risk: float = 0.15,
                 min_hunter_strength: float = 0.8,
                 protect_fertile_female: bool = True,
                 hunter_ratio: float = 0.3,
                 menstrual_hunt_avoidance_rate: float = 0.85,
                 days_per_month: int = 30,
                 menstrual_low_eff_days: int = 5,
                 pregnancy_no_hunt_from_month: int = 1):
        self.hunting_risk = hunting_risk
        self.min_hunter_strength = min_hunter_strength
        self.protect_fertile_female = protect_fertile_female
        self.hunter_ratio = hunter_ratio
        self.menstrual_hunt_avoidance_rate = menstrual_hunt_avoidance_rate
        self.days_per_month = days_per_month
        self.menstrual_low_eff_days = menstrual_low_eff_days
        self.pregnancy_no_hunt_from_month = pregnancy_no_hunt_from_month
    
    def apply(self, tribe: Tribe) -> None:
        """为部落成员分配活动"""
        alive = [ind for ind in tribe.individuals.values() if ind.is_alive]
        if not alive:
            return

        # 统一能力驱动分配：不再依赖三种强弱关系标签
        candidates = []
        for ind in alive:
            # 重置当月状态标记（供后续风险计算使用）
            if hasattr(ind, 'menstruation_active'):
                ind.menstruation_active = False
            else:
                ind.menstruation_active = False

            if not ind.can_hunt:
                continue

            if ind.gender == Gender.FEMALE:
                # 怀孕后尽早停止狩猎，转采集
                if ind.is_pregnant and ind.pregnancy_months >= self.pregnancy_no_hunt_from_month:
                    continue

                # 经期按月概率抽样：更可能规避狩猎，转采集
                if not ind.is_pregnant and ind.fertility_age:
                    menstrual_prob = min(1.0, self.menstrual_low_eff_days / max(1, self.days_per_month))
                    ind.menstruation_active = (np.random.random() < menstrual_prob)
                    if ind.menstruation_active and np.random.random() < self.menstrual_hunt_avoidance_rate:
                        continue

            if ind.effective_strength < self.min_hunter_strength:
                continue
            candidates.append(ind)

        # 受伤者可工作，但效率较低，因此狩猎排序时自然劣后
        all_candidates = sorted(
            candidates,
            key=lambda x: (x.effective_strength * 0.55 + x.effective_intelligence * 0.45) * x.work_efficiency,
            reverse=True
        )
        needed_hunters = max(1, int(len(alive) * self.hunter_ratio))
        hunters = all_candidates[:needed_hunters]
        hunter_ids = {h.id for h in hunters}
        for ind in alive:
            ind.assigned_activity = ActivityType.HUNTING if ind.id in hunter_ids else ActivityType.GATHERING


class ResourceProductionMechanism(BaseMechanism):
    """资源生产机制"""
    
    def __init__(self,
                 meat_protein_content: float = 0.8,      # 肉类蛋白质含量
                 plant_protein_content: float = 0.2,     # 植物蛋白质含量
                 hunting_base_yield: float = 10.0,
                 gathering_base_yield: float = 6.0,
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
    
    def apply(self, tribe: Tribe) -> Tuple[float, float]:
        """
        计算并分配资源
        返回: (meat_yield, plant_yield)
        """
        hunters = tribe.hunters
        gatherers = tribe.gatherers

        # 资源腐败/损耗，避免无限囤积导致人口不现实爆炸
        tribe.food_meat = max(0.0, tribe.food_meat * (1 - self.spoilage_rate * 1.5))
        tribe.food_plant = max(0.0, tribe.food_plant * (1 - self.spoilage_rate))
        
        # 狩猎产出（体力+智力+沟通）
        meat_yield = 0
        for hunter in hunters:
            phys_factor = self._female_cycle_factor(hunter)
            specialization = min(
                self.specialization_cap,
                1.0 + hunter.hunting_experience * self.specialization_hunting_bonus
            )
            efficiency = (hunter.effective_strength * 0.4 +
                         hunter.effective_intelligence * 0.4 +
                         hunter.effective_communication * 0.2) * hunter.work_efficiency * phys_factor * specialization
            # 团队协作加成
            team_bonus = 1 + (len(hunters) - 1) * 0.05
            meat_yield += self.hunting_base_yield * efficiency * team_bonus
        
        # 采集产出（稳定但较低）
        plant_yield = 0
        for gatherer in gatherers:
            phys_factor = self._female_cycle_factor(gatherer)
            specialization = min(
                self.specialization_cap,
                1.0 + gatherer.gathering_experience * self.specialization_gathering_bonus
            )
            efficiency = (
                gatherer.effective_intelligence * 0.3 + gatherer.effective_strength * 0.2 + 0.5
            ) * gatherer.work_efficiency * phys_factor * specialization
            plant_yield += self.gathering_base_yield * efficiency
        
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
    
    def apply(self, tribe: Tribe) -> List[Individual]:
        """应用死亡，返回死亡个体列表"""
        deceased = []
        
        for ind in list(tribe.individuals.values()):
            if not ind.is_alive:
                continue
                
            death_prob = self.base_mortality
            
            # 狩猎死亡/受伤风险
            if ind.assigned_activity == ActivityType.HUNTING:
                death_prob += self.hunting_mortality
                injury_prob = self.hunting_injury

                # 经期狩猎：气味暴露提高风险
                if ind.gender == Gender.FEMALE and getattr(ind, 'menstruation_active', False):
                    death_prob += self.menstrual_hunting_extra_mortality
                    injury_prob += self.menstrual_hunting_extra_injury

                # 怀孕狩猎（理论上已被分工层尽量避免）：若发生，风险更高
                if ind.gender == Gender.FEMALE and ind.is_pregnant:
                    death_prob += self.pregnancy_hunting_extra_mortality
                    injury_prob += self.pregnancy_hunting_extra_injury

                if np.random.random() < injury_prob:
                    ind.injury_level = min(1.0, ind.injury_level + np.random.uniform(0.08, 0.25))
                    ind.injury_months += 1

            # 受伤状态演化：可能好转，也可能恶化
            if ind.is_injured:
                recover_bias = 0.08 if ind.resources >= self.resource_threshold else -0.08
                if np.random.random() < max(0.02, self.injury_recover_rate + recover_bias):
                    ind.injury_level = max(0.0, ind.injury_level - np.random.uniform(0.05, 0.16))
                elif np.random.random() < max(0.02, self.injury_worsen_rate - recover_bias):
                    ind.injury_level = min(1.0, ind.injury_level + np.random.uniform(0.04, 0.14))
                ind.injury_months += 1
                death_prob += ind.injury_level * 0.08
            
            # 怀孕死亡风险
            if ind.is_pregnant:
                death_prob += self.pregnancy_mortality
            
            # 年龄风险
            if ind.age > self.old_age_start:
                death_prob += (ind.age - self.old_age_start) * 0.005
            
            # 婴儿死亡率
            if ind.age < 2:
                death_prob = self.infant_mortality
            
            # 健康度影响（资源不足会降低健康）
            if ind.resources < self.resource_threshold:
                ind.health -= 0.05
                death_prob += 0.02
            elif ind.health < 1.0:
                ind.health = min(1.0, ind.health + 0.01)
            
            # 随机死亡判定
            if np.random.random() < death_prob or ind.health <= 0 or ind.injury_level >= 1.0:
                ind.is_alive = False
                tribe.death_count += 1
                deceased.append(ind)
        
        return deceased

    def apply_crowding_pressure(self, tribe: Tribe, shared_overcrowd_ratio: float) -> List[Individual]:
        """
        承载力压力死亡：使用共享K，当总人口超过总K时各部落都承受额外死亡压力。
        """
        deceased = []
        if tribe.population <= 0 or shared_overcrowd_ratio <= 0:
            return deceased

        extra_death_prob = min(0.25, 0.03 + shared_overcrowd_ratio * 0.12)

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
                 expression_mutation_std: float = 0.02):
        self.gestation_months = gestation_months
        self.fertility_cycle = fertility_cycle
        self.min_resources_for_pregnancy = min_resources_for_pregnancy
        self.male_competition_factor = male_competition_factor
        self.cross_tribe_mating_rate = cross_tribe_mating_rate
        self.inheritance_mutation_std = inheritance_mutation_std
        self.preference_mutation_std = preference_mutation_std
        self.expression_mutation_std = expression_mutation_std
    
    def apply(
        self,
        tribe: Tribe,
        individual_id_counter: int,
        all_tribes: Optional[List[Tribe]] = None,
        shared_k: Optional[float] = None,
        total_population: Optional[int] = None
    ) -> Tuple[List[Individual], int, Dict]:
        """
        处理繁殖
        返回: (新生儿列表, 更新的ID计数器)
        """
        newborns = []
        fertile_females = tribe.fertile_females
        selection_stats = {
            'eligible_males_count': 0,
            'female_choice_events': 0,
            'selected_males_count': 0,
            'conception_events': 0,
            'conceived_males_count': 0,
            'mate_selection_differential': {
                'resource': 0.0,
                'effective_strength': 0.0,
                'effective_intelligence': 0.0,
                'effective_communication': 0.0
            },
            'birth_selection_differential': {
                'resource': 0.0,
                'effective_strength': 0.0,
                'effective_intelligence': 0.0,
                'effective_communication': 0.0
            }
        }
        
        # 允许少量跨部落交配，以降低“完全隔离”导致的结构偏差
        available_males = []
        candidate_tribes = all_tribes or [tribe]
        for t in candidate_tribes:
            if t.id != tribe.id and np.random.random() > self.cross_tribe_mating_rate:
                continue
            for ind in t.individuals.values():
                if ind.is_alive and ind.gender == Gender.MALE and ind.fertility_age and ind.resources >= 0.5:
                    available_males.append(ind)
        
        if not available_males:
            return newborns, individual_id_counter, selection_stats

        selection_stats['eligible_males_count'] = len(available_males)

        def _male_trait_vector(male: Individual) -> Dict[str, float]:
            return {
                'resource': float(male.resources),
                'effective_strength': float(male.effective_strength),
                'effective_intelligence': float(male.effective_intelligence),
                'effective_communication': float(male.effective_communication)
            }

        eligible_traits = [_male_trait_vector(m) for m in available_males]
        selected_male_pool = []
        conceived_male_pool = []
        
        for female in fertile_females:
            # 资源检查 - 需要足够资源才能怀孕
            if tribe.food_meat < self.min_resources_for_pregnancy:
                # 蛋白质不足，降低怀孕概率
                if np.random.random() > 0.1:
                    continue
            
            # 雌性个体偏好驱动择偶：
            # 权重由可遗传参数给出（资源/力量/智力/沟通）
            w_res = female.mate_pref_resource
            w_str = female.mate_pref_strength
            w_int = female.mate_pref_intelligence
            w_com = female.mate_pref_communication

            # 雄性竞争 - 按雌性偏好计算得分
            male_scores = []
            for male in available_males:
                # 资源信号取对数，防止极端资源值完全主导择偶
                resource_signal = min(2.5, np.log1p(max(0.0, male.resources)) * 1.2)
                score = (
                    resource_signal * w_res +
                    male.effective_strength * w_str +
                    male.effective_intelligence * w_int +
                    male.effective_communication * w_com
                )
                male_scores.append((male, score))
            
            male_scores.sort(key=lambda x: x[1], reverse=True)
            
            # 雌性择偶：不再按部落标签硬编码，统一采用“高分偏好 + 探索”
            if male_scores and np.random.random() < (0.5 + self.male_competition_factor * 0.5):
                selected_male = male_scores[0][0]
            else:
                qualified = [m for m, s in male_scores if s >= np.mean([s for _, s in male_scores])]
                selected_male = np.random.choice(qualified if qualified else available_males)

            selection_stats['female_choice_events'] += 1
            selected_male_pool.append(selected_male)
            
            # 怀孕判定
            conception_prob = 0.35  # 基础怀孕概率（提高以维持种群）

            # S曲线承载力约束：所有部落共享K
            if shared_k and shared_k > 0:
                pop = total_population if total_population is not None else tribe.population
                density = pop / shared_k
                if density <= 1:
                    conception_prob *= max(0.35, 1 - density * 0.7)
                else:
                    conception_prob *= max(0.05, 0.25 / density)
            
            # 营养影响
            if tribe.food_meat > self.min_resources_for_pregnancy * 2:
                conception_prob *= 1.3
            
            if np.random.random() < conception_prob:
                female.pregnancy_months = 1
                female.partner_id = selected_male.id
                selection_stats['conception_events'] += 1
                conceived_male_pool.append(selected_male)
        
        # 处理已有怀孕
        pregnant_females = [ind for ind in tribe.individuals.values()
                           if ind.is_alive and ind.gender == Gender.FEMALE 
                           and ind.is_pregnant]
        
        for female in pregnant_females:
            female.pregnancy_months += 1
            
            # 营养消耗（确保不变成负数）
            tribe.food_meat = max(0, tribe.food_meat - 0.5)  # 孕期需要更多蛋白质
            
            # 分娩
            if female.pregnancy_months >= self.gestation_months:
                female.pregnancy_months = 0
                
                # 子代关系由父母共同决定，再叠加少量突变
                father = None
                if female.partner_id:
                    # 分娩时父系追溯应在全体部落范围，而非受当月跨部落抽样影响
                    for t in (all_tribes or [tribe]):
                        if female.partner_id in t.individuals:
                            father = t.individuals[female.partner_id]
                            break

                # 不再使用三种关系做主要建模，统一使用 EQUAL 标签，
                # 个体差异通过连续能力值遗传与变异表达。
                child_relation = GenderStrengthRelation.EQUAL
                
                # 随机性别
                child_gender = np.random.choice([Gender.MALE, Gender.FEMALE])
                
                # 创建新生儿
                newborn = Individual(
                    id=individual_id_counter,
                    gender=child_gender,
                    strength_relation=child_relation,
                    age=0
                )
                
                # 继承父母属性（回归平均）
                if father is not None:
                    # 仅继承先天基线；后天训练结果不遗传
                    newborn.innate_strength = (
                        (father.innate_strength + female.innate_strength) / 2
                        + np.random.normal(0, self.inheritance_mutation_std)
                    )
                    newborn.innate_intelligence = (
                        (father.innate_intelligence + female.innate_intelligence) / 2
                        + np.random.normal(0, self.inheritance_mutation_std)
                    )
                    newborn.innate_communication = (
                        (father.innate_communication + female.innate_communication) / 2
                        + np.random.normal(0, self.inheritance_mutation_std)
                    )
                    newborn.expr_strength_male = min(
                        1.35,
                        max(
                            0.7,
                            (father.expr_strength_male + female.expr_strength_male) / 2
                            + np.random.normal(0, self.expression_mutation_std)
                        )
                    )
                    newborn.expr_strength_female = min(
                        1.35,
                        max(
                            0.7,
                            (father.expr_strength_female + female.expr_strength_female) / 2
                            + np.random.normal(0, self.expression_mutation_std)
                        )
                    )
                    newborn.strength = max(0.5, newborn.innate_strength)
                    newborn.intelligence = max(0.5, newborn.innate_intelligence)
                    newborn.communication = max(0.5, newborn.innate_communication)

                    # 择偶偏好也遗传（父母平均 + 小突变），并归一化
                    newborn.mate_pref_resource = (
                        (father.mate_pref_resource + female.mate_pref_resource) / 2
                        + np.random.normal(0, self.preference_mutation_std)
                    )
                    newborn.mate_pref_strength = (
                        (father.mate_pref_strength + female.mate_pref_strength) / 2
                        + np.random.normal(0, self.preference_mutation_std)
                    )
                    newborn.mate_pref_intelligence = (
                        (father.mate_pref_intelligence + female.mate_pref_intelligence) / 2
                        + np.random.normal(0, self.preference_mutation_std)
                    )
                    newborn.mate_pref_communication = (
                        (father.mate_pref_communication + female.mate_pref_communication) / 2
                        + np.random.normal(0, self.preference_mutation_std)
                    )
                    newborn._normalize_mate_preferences()
                    father.children.append(newborn.id)
                else:
                    newborn.innate_strength = max(0.5, female.innate_strength + np.random.normal(0, 0.04))
                    newborn.innate_intelligence = max(0.5, female.innate_intelligence + np.random.normal(0, 0.04))
                    newborn.innate_communication = max(0.5, female.innate_communication + np.random.normal(0, 0.04))
                    newborn.expr_strength_male = min(
                        1.35,
                        max(0.7, female.expr_strength_male + np.random.normal(0, self.expression_mutation_std))
                    )
                    newborn.expr_strength_female = min(
                        1.35,
                        max(0.7, female.expr_strength_female + np.random.normal(0, self.expression_mutation_std))
                    )
                    newborn.strength = newborn.innate_strength
                    newborn.intelligence = newborn.innate_intelligence
                    newborn.communication = newborn.innate_communication
                    newborn.mate_pref_resource = female.mate_pref_resource + np.random.normal(0, self.preference_mutation_std)
                    newborn.mate_pref_strength = female.mate_pref_strength + np.random.normal(0, self.preference_mutation_std)
                    newborn.mate_pref_intelligence = female.mate_pref_intelligence + np.random.normal(0, self.preference_mutation_std)
                    newborn.mate_pref_communication = female.mate_pref_communication + np.random.normal(0, self.preference_mutation_std)
                    newborn._normalize_mate_preferences()
                
                female.children.append(newborn.id)
                newborns.append(newborn)
                tribe.birth_count += 1
                individual_id_counter += 1

        selection_stats['selected_males_count'] = len({m.id for m in selected_male_pool})
        selection_stats['conceived_males_count'] = len({m.id for m in conceived_male_pool})

        def _mean_traits(pool: List[Individual]) -> Dict[str, float]:
            if not pool:
                return {
                    'resource': 0.0,
                    'effective_strength': 0.0,
                    'effective_intelligence': 0.0,
                    'effective_communication': 0.0
                }
            vals = [_male_trait_vector(m) for m in pool]
            return {
                k: float(np.mean([v[k] for v in vals]))
                for k in vals[0].keys()
            }

        base_mean = {
            k: float(np.mean([v[k] for v in eligible_traits]))
            for k in eligible_traits[0].keys()
        }
        selected_mean = _mean_traits(selected_male_pool)
        conceived_mean = _mean_traits(conceived_male_pool)
        selection_stats['mate_selection_differential'] = {
            k: selected_mean[k] - base_mean[k] for k in base_mean.keys()
        }
        selection_stats['birth_selection_differential'] = {
            k: conceived_mean[k] - base_mean[k] for k in base_mean.keys()
        }

        return newborns, individual_id_counter, selection_stats


class ResourceDistributionMechanism(BaseMechanism):
    """资源分配机制"""
    
    def __init__(self,
                 base_consumption: float = 2.0,
                 pregnancy_extra: float = 1.5,
                 hunter_bonus: float = 0.3,
                 strength_metabolic_scale: float = 0.22,
                 child_priority: bool = True):
        self.base_consumption = base_consumption
        self.pregnancy_extra = pregnancy_extra
        self.hunter_bonus = hunter_bonus
        self.strength_metabolic_scale = strength_metabolic_scale
        self.child_priority = child_priority
    
    def apply(self, tribe: Tribe) -> None:
        """分配资源给个体"""
        alive_individuals = [ind for ind in tribe.individuals.values() if ind.is_alive]
        
        if not alive_individuals:
            return
        
        # 总需求
        total_need = 0
        individual_needs = {}
        
        for ind in alive_individuals:
            need = self.base_consumption
            if ind.is_pregnant:
                need += self.pregnancy_extra
            if ind.assigned_activity == ActivityType.HUNTING:
                need += self.hunter_bonus  # 狩猎者需要更多能量
            # 体能与体格代谢成本：不是性别惩罚，而是能力代价
            need += max(0.0, ind.effective_strength - 0.9) * self.strength_metabolic_scale
            
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

    def apply(self, tribe: Tribe) -> None:
        for ind in tribe.individuals.values():
            if not ind.is_alive:
                continue

            # 基于工作的经验积累与属性塑形
            if ind.assigned_activity == ActivityType.HUNTING:
                ind.hunting_experience += self.hunting_exp_gain
                ind.gathering_experience = max(0.0, ind.gathering_experience - self.cross_decay)
                ind.strength += self.hunt_strength_gain * (1 + 0.05 * ind.hunting_experience)
                ind.intelligence += self.hunt_intelligence_gain * (1 + 0.05 * ind.hunting_experience)
                ind.communication += self.hunt_communication_gain * (1 + 0.05 * ind.hunting_experience)
            elif ind.assigned_activity == ActivityType.GATHERING:
                ind.gathering_experience += self.gathering_exp_gain
                ind.hunting_experience = max(0.0, ind.hunting_experience - self.cross_decay)
                ind.strength += self.gather_strength_gain * (1 + 0.05 * ind.gathering_experience)
                ind.intelligence += self.gather_intelligence_gain * (1 + 0.05 * ind.gathering_experience)
                ind.communication += self.gather_communication_gain * (1 + 0.05 * ind.gathering_experience)

            # 环境约束：资源不足时属性表现下降
            if ind.resources < self.resource_penalty_threshold:
                ind.strength = max(0.5, ind.strength - self.starvation_attr_penalty)
                ind.intelligence = max(0.5, ind.intelligence - self.starvation_attr_penalty * 0.6)
                ind.communication = max(0.5, ind.communication - self.starvation_attr_penalty * 0.6)

            # 基因基线回拉：表现型受先天约束，但可被环境塑形
            ind.strength += (ind.innate_strength - ind.strength) * self.innate_pull_rate
            ind.intelligence += (ind.innate_intelligence - ind.intelligence) * self.innate_pull_rate
            ind.communication += (ind.innate_communication - ind.communication) * self.innate_pull_rate

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
                    tribe1.total_resources += transfer
                    tribe2.total_resources = max(0, tribe2.total_resources - transfer)
                    tribe1.food_meat += transfer * 0.6
                    tribe2.food_meat = max(0, tribe2.food_meat - transfer * 0.6)
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
                    tribe2.total_resources += transfer
                    tribe1.total_resources = max(0, tribe1.total_resources - transfer)
                    tribe2.food_meat += transfer * 0.6
                    tribe1.food_meat = max(0, tribe1.food_meat - transfer * 0.6)
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


class AgingMechanism(BaseMechanism):
    """老化机制"""
    
    def __init__(self, months_per_year: int = 12):
        self.months_per_year = months_per_year
    
    def apply(self, tribe: Tribe) -> None:
        """增加年龄"""
        for ind in tribe.individuals.values():
            if ind.is_alive:
                ind.age += 1 / self.months_per_year  # 每月增加年龄
