"""
核心生物模型和实体定义
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from enum import Enum, auto
import numpy as np


class Gender(Enum):
    """性别枚举"""
    MALE = auto()
    FEMALE = auto()


class ActivityType(Enum):
    """活动类型"""
    HUNTING = auto()    # 狩猎
    GATHERING = auto()  # 采集


class GenderStrengthRelation(Enum):
    """性别强弱关系类型"""
    MALE_STRONGER = 1    # 雄稍强雌稍弱（智人模式）
    FEMALE_STRONGER = 2  # 雌稍强雄稍弱
    EQUAL = 3            # 雌雄相当


@dataclass
class Individual:
    """个体实体"""
    id: int
    gender: Gender
    strength_relation: GenderStrengthRelation
    
    # 基础属性
    strength: float = 1.0           # 体力（后天可塑基线，不含表达调制）
    intelligence: float = 1.0        # 智力
    communication: float = 1.0       # 沟通能力
    expr_strength_male: float = 1.0      # 力量表达基因（在雄性体内的表达系数）
    expr_strength_female: float = 1.0    # 力量表达基因（在雌性体内的表达系数）
    mate_pref_resource: float = 0.3      # 择偶偏好：资源权重（可遗传）
    mate_pref_strength: float = 0.3      # 择偶偏好：力量权重（可遗传）
    mate_pref_intelligence: float = 0.2  # 择偶偏好：智力权重（可遗传）
    mate_pref_communication: float = 0.2 # 择偶偏好：沟通权重（可遗传）
    innate_strength: float = 1.0     # 先天体力（可遗传）
    innate_intelligence: float = 1.0 # 先天智力（可遗传）
    innate_communication: float = 1.0# 先天沟通（可遗传）
    hunting_experience: float = 0.0  # 狩猎经验（后天，不遗传）
    gathering_experience: float = 0.0# 采集经验（后天，不遗传）
    age: int = 0                     # 年龄
    
    # 生存状态
    health: float = 1.0              # 健康度 (0-1)
    resources: float = 0.0           # 资源拥有量
    is_alive: bool = True            # 是否存活
    injury_level: float = 0.0        # 受伤程度 (0-1)
    injury_months: int = 0           # 持续受伤月数
    
    # 繁殖相关
    children: List[int] = field(default_factory=list)  # 子代ID列表
    pregnancy_months: int = 0        # 怀孕月数（雌性）
    partner_id: Optional[int] = None # 配偶ID
    
    # 活动分配
    assigned_activity: Optional[ActivityType] = None
    
    def __post_init__(self):
        # 统一能力初始化：雌雄同分布，避免初始性别偏置
        self.strength = np.random.normal(1.0, 0.1)
        self.intelligence = np.random.normal(1.0, 0.08)
        
        # 确保数值在合理范围内
        self.strength = max(0.5, self.strength)
        self.intelligence = max(0.5, self.intelligence)
        self.communication = max(0.5, self.communication)
        # 初始先天基线等于初始表现型
        self.innate_strength = self.strength
        self.innate_intelligence = self.intelligence
        self.innate_communication = self.communication
        # 性别特异表达基因：初代对称随机，无预设方向
        base_expr = np.random.normal(1.0, 0.04)
        delta_expr = np.random.normal(0.0, 0.03)
        self.expr_strength_male = min(1.35, max(0.7, base_expr + delta_expr))
        self.expr_strength_female = min(1.35, max(0.7, base_expr - delta_expr))
        self.injury_level = min(1.0, max(0.0, self.injury_level))
        # 默认值不设为完全固定，避免初始世代所有个体偏好同质
        if (
            abs(self.mate_pref_resource - 0.3) < 1e-9 and
            abs(self.mate_pref_strength - 0.3) < 1e-9 and
            abs(self.mate_pref_intelligence - 0.2) < 1e-9 and
            abs(self.mate_pref_communication - 0.2) < 1e-9
        ):
            pref = np.random.dirichlet(np.array([6.0, 6.0, 4.0, 4.0], dtype=float))
            self.mate_pref_resource = float(pref[0])
            self.mate_pref_strength = float(pref[1])
            self.mate_pref_intelligence = float(pref[2])
            self.mate_pref_communication = float(pref[3])
        self._normalize_mate_preferences()

    def _normalize_mate_preferences(self):
        """归一化择偶偏好权重，确保四项非负且和为1"""
        vals = np.array([
            self.mate_pref_resource,
            self.mate_pref_strength,
            self.mate_pref_intelligence,
            self.mate_pref_communication
        ], dtype=float)
        vals = np.where(np.isfinite(vals), vals, 0.0)
        vals = np.maximum(0.0, vals)
        total = float(np.sum(vals))
        if total <= 1e-12:
            vals = np.random.dirichlet(np.array([6.0, 6.0, 4.0, 4.0], dtype=float))
        else:
            vals = vals / total
        self.mate_pref_resource = float(vals[0])
        self.mate_pref_strength = float(vals[1])
        self.mate_pref_intelligence = float(vals[2])
        self.mate_pref_communication = float(vals[3])
    
    @property
    def can_hunt(self) -> bool:
        """是否能参与狩猎（体力和智力要求）"""
        # 显式括号避免 and/or 优先级歧义：
        # 1) 成年雄性达到基础阈值可狩猎
        # 2) 其他个体只有在更高能力阈值下才可狩猎
        if not (16 <= self.age <= 45):
            return False
        return (
            (self.gender == Gender.MALE and self.effective_strength > 0.8 and self.effective_intelligence > 0.7)
            or (self.effective_strength > 1.0 and self.effective_intelligence > 0.9)
        )

    @property
    def is_injured(self) -> bool:
        """是否处于受伤状态"""
        return self.injury_level > 0.01

    @property
    def work_efficiency(self) -> float:
        """工作效率系数（受伤会降低效率）"""
        # 受伤影响能力输出，但不强制失去工作能力
        return max(0.15, 1.0 - self.injury_level * 0.75)

    @property
    def age_factor(self) -> float:
        """
        年龄对能力表现的影响（石器时代简化近似）：
        - 青少年逐步增长
        - 青壮年维持高水平
        - 中老年逐步下降
        """
        if self.age < 12:
            return 0.55
        if self.age < 20:
            return 0.55 + (self.age - 12) * (0.4 / 8)   # 0.55 -> 0.95
        if self.age < 35:
            return 1.0
        if self.age < 50:
            return 1.0 - (self.age - 35) * (0.12 / 15)  # 1.0 -> 0.88
        if self.age < 65:
            return 0.88 - (self.age - 50) * (0.23 / 15) # 0.88 -> 0.65
        return max(0.45, 0.65 - (self.age - 65) * 0.02)

    @property
    def effective_strength(self) -> float:
        """年龄与健康共同作用下的有效力量"""
        return self.phenotype_strength * self.age_factor * (0.8 + 0.2 * self.health)

    @property
    def phenotype_strength(self) -> float:
        """
        后天表现型力量（用于统计口径）：
        先天基线受后天训练/环境塑形后的 strength，
        再叠加性别特异表达系数。
        """
        expr = self.expr_strength_male if self.gender == Gender.MALE else self.expr_strength_female
        return self.strength * expr

    @property
    def effective_intelligence(self) -> float:
        """年龄与健康共同作用下的有效智力"""
        return self.intelligence * self.age_factor * (0.85 + 0.15 * self.health)

    @property
    def effective_communication(self) -> float:
        """年龄与健康共同作用下的有效沟通能力"""
        return self.communication * self.age_factor * (0.85 + 0.15 * self.health)
    
    @property
    def fertility_age(self) -> bool:
        """是否在生育年龄"""
        return 15 <= self.age <= 45 if self.gender == Gender.FEMALE else 15 <= self.age <= 60

    @property
    def mate_preference_type(self) -> str:
        """主导择偶偏好类型（用于统计）"""
        prefs = {
            'resource': self.mate_pref_resource,
            'strength': self.mate_pref_strength,
            'intelligence': self.mate_pref_intelligence,
            'communication': self.mate_pref_communication
        }
        spread = max(prefs.values()) - min(prefs.values())
        if spread < 0.08:
            return 'balanced'
        return max(prefs.items(), key=lambda x: x[1])[0]
    
    @property
    def is_pregnant(self) -> bool:
        """是否怀孕"""
        return self.pregnancy_months > 0
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'id': self.id,
            'gender': self.gender.name,
            'strength_relation': self.strength_relation.value,
            'strength': self.strength,
            'intelligence': self.intelligence,
            'communication': self.communication,
            'expr_strength_male': self.expr_strength_male,
            'expr_strength_female': self.expr_strength_female,
            'mate_pref_resource': self.mate_pref_resource,
            'mate_pref_strength': self.mate_pref_strength,
            'mate_pref_intelligence': self.mate_pref_intelligence,
            'mate_pref_communication': self.mate_pref_communication,
            'innate_strength': self.innate_strength,
            'innate_intelligence': self.innate_intelligence,
            'innate_communication': self.innate_communication,
            'hunting_experience': self.hunting_experience,
            'gathering_experience': self.gathering_experience,
            'age': self.age,
            'health': self.health,
            'resources': self.resources,
            'is_alive': self.is_alive,
            'injury_level': self.injury_level,
            'injury_months': self.injury_months,
            'children': self.children,
            'pregnancy_months': self.pregnancy_months,
            'partner_id': self.partner_id,
            'assigned_activity': self.assigned_activity.name if self.assigned_activity else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Individual':
        """从字典反序列化"""
        ind = cls(
            id=data['id'],
            gender=Gender[data['gender']],
            strength_relation=GenderStrengthRelation(data['strength_relation'])
        )
        ind.strength = data['strength']
        ind.intelligence = data['intelligence']
        ind.communication = data['communication']
        ind.expr_strength_male = data.get('expr_strength_male', 1.0)
        ind.expr_strength_female = data.get('expr_strength_female', 1.0)
        ind.mate_pref_resource = data.get('mate_pref_resource', 0.3)
        ind.mate_pref_strength = data.get('mate_pref_strength', 0.3)
        ind.mate_pref_intelligence = data.get('mate_pref_intelligence', 0.2)
        ind.mate_pref_communication = data.get('mate_pref_communication', 0.2)
        ind._normalize_mate_preferences()
        ind.innate_strength = data.get('innate_strength', ind.strength)
        ind.innate_intelligence = data.get('innate_intelligence', ind.intelligence)
        ind.innate_communication = data.get('innate_communication', ind.communication)
        ind.hunting_experience = data.get('hunting_experience', 0.0)
        ind.gathering_experience = data.get('gathering_experience', 0.0)
        ind.age = data['age']
        ind.health = data['health']
        ind.resources = data['resources']
        ind.is_alive = data['is_alive']
        ind.injury_level = data.get('injury_level', 0.0)
        ind.injury_months = data.get('injury_months', 0)
        ind.children = data['children']
        ind.pregnancy_months = data['pregnancy_months']
        ind.partner_id = data['partner_id']
        ind.assigned_activity = ActivityType[data['assigned_activity']] if data['assigned_activity'] else None
        return ind


@dataclass
class Tribe:
    """部落实体"""
    id: int
    strength_relation: GenderStrengthRelation
    individuals: Dict[int, Individual] = field(default_factory=dict)
    
    # 部落资源
    total_resources: float = 0.0
    food_meat: float = 0.0        # 肉类资源（高蛋白/脂质）
    food_plant: float = 0.0       # 植物资源
    
    # 历史记录
    population_history: List[int] = field(default_factory=list)
    resource_history: List[float] = field(default_factory=list)
    birth_count: int = 0
    death_count: int = 0
    
    def __post_init__(self):
        self.population_history = []
        self.resource_history = []
    
    @property
    def population(self) -> int:
        """当前人口"""
        return sum(1 for ind in self.individuals.values() if ind.is_alive)
    
    @property
    def female_count(self) -> int:
        """雌性数量"""
        return sum(1 for ind in self.individuals.values() 
                   if ind.is_alive and ind.gender == Gender.FEMALE)
    
    @property
    def male_count(self) -> int:
        """雄性数量"""
        return sum(1 for ind in self.individuals.values() 
                   if ind.is_alive and ind.gender == Gender.MALE)
    
    @property
    def hunters(self) -> List[Individual]:
        """当前猎人列表"""
        return [ind for ind in self.individuals.values() 
                if ind.is_alive and ind.assigned_activity == ActivityType.HUNTING]
    
    @property
    def gatherers(self) -> List[Individual]:
        """当前采集者列表"""
        return [ind for ind in self.individuals.values() 
                if ind.is_alive and ind.assigned_activity == ActivityType.GATHERING]
    
    @property
    def fertile_females(self) -> List[Individual]:
        """可生育雌性"""
        return [ind for ind in self.individuals.values()
                if ind.is_alive and ind.gender == Gender.FEMALE 
                and ind.fertility_age and not ind.is_pregnant]

    @property
    def injured_count(self) -> int:
        """受伤个体数"""
        return sum(1 for ind in self.individuals.values() if ind.is_alive and ind.is_injured)

    @property
    def alive_males(self) -> List[Individual]:
        """存活雄性个体"""
        return [
            ind for ind in self.individuals.values()
            if ind.is_alive and ind.gender == Gender.MALE
        ]

    @property
    def alive_females(self) -> List[Individual]:
        """存活雌性个体"""
        return [
            ind for ind in self.individuals.values()
            if ind.is_alive and ind.gender == Gender.FEMALE
        ]

    @property
    def avg_male_strength(self) -> float:
        """雄性平均力量"""
        males = self.alive_males
        return float(np.mean([m.phenotype_strength for m in males])) if males else 0.0

    @property
    def avg_female_strength(self) -> float:
        """雌性平均力量"""
        females = self.alive_females
        return float(np.mean([f.phenotype_strength for f in females])) if females else 0.0

    @property
    def median_male_strength(self) -> float:
        """雄性表现型力量中位数"""
        males = self.alive_males
        return float(np.median([m.phenotype_strength for m in males])) if males else 0.0

    @property
    def median_female_strength(self) -> float:
        """雌性表现型力量中位数"""
        females = self.alive_females
        return float(np.median([f.phenotype_strength for f in females])) if females else 0.0

    @property
    def avg_male_innate_strength(self) -> float:
        """雄性先天力量平均值"""
        males = self.alive_males
        return float(np.mean([m.innate_strength for m in males])) if males else 0.0

    @property
    def avg_female_innate_strength(self) -> float:
        """雌性先天力量平均值"""
        females = self.alive_females
        return float(np.mean([f.innate_strength for f in females])) if females else 0.0

    @property
    def avg_male_strength_expression(self) -> float:
        """雄性个体体内的力量表达系数均值"""
        males = self.alive_males
        return float(np.mean([m.expr_strength_male for m in males])) if males else 0.0

    @property
    def avg_female_strength_expression(self) -> float:
        """雌性个体体内的力量表达系数均值"""
        females = self.alive_females
        return float(np.mean([f.expr_strength_female for f in females])) if females else 0.0

    @property
    def median_male_innate_strength(self) -> float:
        """雄性先天力量中位数"""
        males = self.alive_males
        return float(np.median([m.innate_strength for m in males])) if males else 0.0

    @property
    def median_female_innate_strength(self) -> float:
        """雌性先天力量中位数"""
        females = self.alive_females
        return float(np.median([f.innate_strength for f in females])) if females else 0.0

    @property
    def female_mate_preference_ratios(self) -> Dict[str, float]:
        """存活雌性的择偶偏好占比"""
        females = self.alive_females
        if not females:
            return {
                'resource': 0.0,
                'strength': 0.0,
                'intelligence': 0.0,
                'communication': 0.0,
                'balanced': 0.0
            }
        counts = {
            'resource': 0,
            'strength': 0,
            'intelligence': 0,
            'communication': 0,
            'balanced': 0
        }
        for f in females:
            counts[f.mate_preference_type] += 1
        total = float(len(females))
        return {k: v / total for k, v in counts.items()}

    @property
    def dominant_female_mate_preference(self) -> str:
        """雌性主导择偶偏好类型"""
        ratios = self.female_mate_preference_ratios
        return max(ratios.items(), key=lambda x: x[1])[0]

    @property
    def relation_counts(self) -> Dict[GenderStrengthRelation, int]:
        """当前存活个体的强弱关系计数"""
        counts = {r: 0 for r in GenderStrengthRelation}
        for ind in self.individuals.values():
            if ind.is_alive:
                counts[ind.strength_relation] += 1
        return counts

    @property
    def dominant_relation(self) -> GenderStrengthRelation:
        """当前部落内占比最高的强弱关系"""
        counts = self.relation_counts
        return max(counts.items(), key=lambda x: x[1])[0]
    
    @property
    def productive_capacity(self) -> float:
        """生产力评估"""
        if self.population <= 0:
            return 0.0
        alive = [ind for ind in self.individuals.values() if ind.is_alive]
        if not alive:
            return 0.0
        avg_eff = np.mean([
            (ind.effective_strength * 0.4 + ind.effective_intelligence * 0.4 + ind.effective_communication * 0.2)
            for ind in alive
        ])
        return (len(self.hunters) * 2.0 + len(self.gatherers) * 1.0) * avg_eff
    
    @property
    def violence_capacity(self) -> float:
        """暴力能力评估（狩猎能力转化为战斗力）"""
        hunters = self.hunters
        if not hunters:
            return 0
        return sum(h.effective_strength * h.effective_intelligence * h.health for h in hunters)
    
    def add_individual(self, individual: Individual):
        """添加个体"""
        self.individuals[individual.id] = individual
    
    def record_history(self):
        """记录当前状态到历史"""
        self.population_history.append(self.population)
        self.resource_history.append(self.total_resources)
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'id': self.id,
            'strength_relation': self.strength_relation.value,
            'individuals': {k: v.to_dict() for k, v in self.individuals.items()},
            'total_resources': self.total_resources,
            'food_meat': self.food_meat,
            'food_plant': self.food_plant,
            'population_history': self.population_history,
            'resource_history': self.resource_history,
            'birth_count': self.birth_count,
            'death_count': self.death_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Tribe':
        """从字典反序列化"""
        tribe = cls(
            id=data['id'],
            strength_relation=GenderStrengthRelation(data['strength_relation'])
        )
        tribe.individuals = {int(k): Individual.from_dict(v) 
                            for k, v in data['individuals'].items()}
        tribe.total_resources = data['total_resources']
        tribe.food_meat = data['food_meat']
        tribe.food_plant = data['food_plant']
        tribe.population_history = data['population_history']
        tribe.resource_history = data['resource_history']
        tribe.birth_count = data['birth_count']
        tribe.death_count = data['death_count']
        return tribe
