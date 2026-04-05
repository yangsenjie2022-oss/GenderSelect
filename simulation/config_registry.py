"""
配置注册表 - 集中管理所有可配置参数
"""
from typing import Dict, Any
from copy import deepcopy
from .simulator import SimulationConfig


class ConfigRegistry:
    """配置注册表"""
    
    # 预设配置
    PRESETS = {
        'default': {
            'description': '默认配置 - 能力驱动分工 + 受伤机制',
            'config': {
                'initial_population': 120,
                'max_simulation_months': 1200,
                'base_k': 500,
                'population_structure': 'ability_multi_tribe',
                'tribe_count': 4,
                'split_population_threshold': 600,
                'split_probability_full_population': 1000,
                'split_ratio_sigma': 0.12,
                'split_peer_population_ratio_low': 0.8,
                'split_peer_population_ratio_high': 1.25,
                'split_min_child_vs_opponent_ratio': 0.6,
                'checkpoint_interval': 100
            },
            'mechanisms': {
                'activity': {
                    'hunting_risk': 0.05,
                    'min_hunter_strength': 0.65,
                    'protect_fertile_female': True,
                    'hunter_ratio': 0.3
                },
                'production': {
                    'meat_protein_content': 0.8,
                    'plant_protein_content': 0.2,
                    'hunting_base_yield': 18.0,
                    'gathering_base_yield': 11.0,
                    'spoilage_rate': 0.08,
                    'specialization_hunting_bonus': 0.09,
                    'specialization_gathering_bonus': 0.08
                },
                'mortality': {
                    'base_mortality': 0.001,
                    'hunting_mortality': 0.008,
                    'hunting_injury': 0.16,
                    'pregnancy_mortality': 0.001,
                    'infant_mortality': 0.01,
                    'old_age_start': 65,
                    'resource_threshold': 0.5,
                    'injury_worsen_rate': 0.2,
                    'injury_recover_rate': 0.3
                },
                'reproduction': {
                    'gestation_months': 9,
                    'fertility_cycle': 1,
                    'min_resources_for_pregnancy': 1.0,
                    'male_competition_factor': 0.3,
                    'cross_tribe_mating_rate': 0.05
                },
                'distribution': {
                    'base_consumption': 1.2,
                    'pregnancy_extra': 0.8,
                    'hunter_bonus': 0.15,
                    'child_priority': True
                },
                'adaptation': {
                    'hunting_exp_gain': 0.14,
                    'gathering_exp_gain': 0.12,
                    'cross_decay': 0.04,
                    'hunt_strength_gain': 0.006,
                    'hunt_intelligence_gain': 0.003,
                    'hunt_communication_gain': 0.003,
                    'gather_strength_gain': 0.002,
                    'gather_intelligence_gain': 0.006,
                    'gather_communication_gain': 0.005,
                    'adaptation_cap_delta': 0.35,
                    'innate_pull_rate': 0.03
                },
                'competition': {
                    'competition_probability': 0.03,
                    'resource_transfer_rate': 0.08,
                    'population_pressure_factor': 0.2,
                    'battle_casualty_scale': 0.07,
                    'battle_injury_scale': 0.16
                }
            }
        },
        
        'harsh_environment': {
            'description': '恶劣环境 - 高伤亡、恢复慢',
            'config': {
                'initial_population': 160,
                'max_simulation_months': 1200,
                'base_k': 420,
                'population_structure': 'ability_multi_tribe',
                'tribe_count': 4,
                'checkpoint_interval': 100
            },
            'mechanisms': {
                'activity': {
                    'hunting_risk': 0.06,
                    'min_hunter_strength': 0.68,
                    'protect_fertile_female': True
                },
                'production': {
                    'meat_protein_content': 0.9,
                    'plant_protein_content': 0.15,
                    'hunting_base_yield': 17.0,
                    'gathering_base_yield': 10.0,
                    'spoilage_rate': 0.085
                },
                'mortality': {
                    'base_mortality': 0.002,
                    'hunting_mortality': 0.018,
                    'hunting_injury': 0.09,
                    'pregnancy_mortality': 0.004,
                    'infant_mortality': 0.02,
                    'old_age_start': 58,
                    'injury_worsen_rate': 0.13,
                    'injury_recover_rate': 0.38
                },
                'reproduction': {
                    'gestation_months': 9,
                    'fertility_cycle': 1,
                    'min_resources_for_pregnancy': 1.5,
                    'male_competition_factor': 0.35
                },
                'distribution': {
                    'base_consumption': 1.25,
                    'pregnancy_extra': 0.9,
                    'hunter_bonus': 0.18,
                    'child_priority': True
                },
                'adaptation': {
                    'hunting_exp_gain': 0.1,
                    'gathering_exp_gain': 0.1,
                    'cross_decay': 0.05,
                    'adaptation_cap_delta': 0.3,
                    'innate_pull_rate': 0.04,
                    'starvation_attr_penalty': 0.015
                },
                'competition': {
                    'competition_probability': 0.02,
                    'resource_transfer_rate': 0.10,
                    'population_pressure_factor': 0.7,
                    'battle_casualty_scale': 0.025,
                    'battle_injury_scale': 0.07
                }
            }
        },
        
        'abundant_environment': {
            'description': '丰饶环境 - 低风险、恢复快',
            'config': {
                'initial_population': 100,
                'max_simulation_months': 1200,
                'base_k': 500,
                'population_structure': 'ability_multi_tribe',
                'tribe_count': 4,
                'checkpoint_interval': 100
            },
            'mechanisms': {
                'activity': {
                    'hunting_risk': 0.03,
                    'min_hunter_strength': 0.6,
                    'protect_fertile_female': True
                },
                'production': {
                    'meat_protein_content': 0.8,
                    'plant_protein_content': 0.2,
                    'hunting_base_yield': 30.0,
                    'gathering_base_yield': 20.0,
                    'spoilage_rate': 0.04
                },
                'mortality': {
                    'base_mortality': 0.0005,
                    'hunting_mortality': 0.005,
                    'hunting_injury': 0.08,
                    'pregnancy_mortality': 0.0005,
                    'infant_mortality': 0.005,
                    'old_age_start': 70,
                    'resource_threshold': 0.3,
                    'injury_worsen_rate': 0.12,
                    'injury_recover_rate': 0.45
                },
                'reproduction': {
                    'gestation_months': 9,
                    'fertility_cycle': 1,
                    'min_resources_for_pregnancy': 0.5,
                    'male_competition_factor': 0.3
                },
                'distribution': {
                    'base_consumption': 0.8,
                    'pregnancy_extra': 0.5,
                    'hunter_bonus': 0.1,
                    'child_priority': True
                },
                'adaptation': {
                    'hunting_exp_gain': 0.16,
                    'gathering_exp_gain': 0.14,
                    'cross_decay': 0.03,
                    'adaptation_cap_delta': 0.4,
                    'innate_pull_rate': 0.025,
                    'starvation_attr_penalty': 0.006
                },
                'competition': {
                    'competition_probability': 0.02,
                    'resource_transfer_rate': 0.05,
                    'population_pressure_factor': 0.1,
                    'battle_casualty_scale': 0.04,
                    'battle_injury_scale': 0.1
                }
            }
        },
        
        'intense_competition': {
            'description': '激烈竞争 - 部落间冲突频繁',
            'config': {
                'initial_population': 120,
                'max_simulation_months': 1200,
                'base_k': 400,
                'population_structure': 'ability_multi_tribe',
                'tribe_count': 4,
                'checkpoint_interval': 100
            },
            'mechanisms': {
                'activity': {
                    'hunting_risk': 0.07,
                    'min_hunter_strength': 0.66,
                    'protect_fertile_female': True
                },
                'production': {
                    'meat_protein_content': 0.8,
                    'plant_protein_content': 0.2,
                    'hunting_base_yield': 17.0,
                    'gathering_base_yield': 10.0,
                    'spoilage_rate': 0.09
                },
                'mortality': {
                    'base_mortality': 0.0025,
                    'hunting_mortality': 0.022,
                    'hunting_injury': 0.095,
                    'pregnancy_mortality': 0.006,
                    'infant_mortality': 0.022,
                    'old_age_start': 58,
                    'injury_worsen_rate': 0.13,
                    'injury_recover_rate': 0.36
                },
                'reproduction': {
                    'gestation_months': 9,
                    'fertility_cycle': 1,
                    'min_resources_for_pregnancy': 1.5,
                    'male_competition_factor': 0.35
                },
                'distribution': {
                    'base_consumption': 1.25,
                    'pregnancy_extra': 0.9,
                    'hunter_bonus': 0.18,
                    'child_priority': True
                },
                'adaptation': {
                    'hunting_exp_gain': 0.15,
                    'gathering_exp_gain': 0.11,
                    'cross_decay': 0.04,
                    'adaptation_cap_delta': 0.33,
                    'innate_pull_rate': 0.03
                },
                'competition': {
                    'competition_probability': 0.03,
                    'resource_transfer_rate': 0.16,
                    'population_pressure_factor': 0.8,
                    'battle_casualty_scale': 0.03,
                    'battle_injury_scale': 0.08
                }
            }
        },
        
        'many_tribes': {
            'description': '更多部落 - 检验跨部落竞争网络',
            'config': {
                'initial_population': 180,
                'max_simulation_months': 1200,
                'base_k': 430,
                'population_structure': 'ability_multi_tribe',
                'tribe_count': 8,
                'split_population_threshold': 600,
                'split_probability_full_population': 1000,
                'split_ratio_sigma': 0.14,
                'split_peer_population_ratio_low': 0.75,
                'split_peer_population_ratio_high': 1.25,
                'split_min_child_vs_opponent_ratio': 0.55,
                'checkpoint_interval': 100
            },
            'mechanisms': {
                'activity': {
                    'hunting_risk': 0.06,
                    'min_hunter_strength': 0.65,
                    'protect_fertile_female': True,
                    'hunter_ratio': 0.28
                },
                'production': {
                    'meat_protein_content': 0.8,
                    'plant_protein_content': 0.2,
                    'hunting_base_yield': 24.0,
                    'gathering_base_yield': 14.0,
                    'spoilage_rate': 0.08
                },
                'mortality': {
                    'base_mortality': 0.002,
                    'hunting_mortality': 0.01,
                    'hunting_injury': 0.2,
                    'pregnancy_mortality': 0.002,
                    'infant_mortality': 0.012,
                    'old_age_start': 62,
                    'resource_threshold': 0.5,
                    'injury_worsen_rate': 0.22,
                    'injury_recover_rate': 0.32
                },
                'reproduction': {
                    'gestation_months': 9,
                    'fertility_cycle': 1,
                    'min_resources_for_pregnancy': 1.0,
                    'male_competition_factor': 0.3,
                    'cross_tribe_mating_rate': 0.1
                },
                'distribution': {
                    'base_consumption': 1.2,
                    'pregnancy_extra': 0.8,
                    'hunter_bonus': 0.15,
                    'child_priority': True
                },
                'adaptation': {
                    'hunting_exp_gain': 0.13,
                    'gathering_exp_gain': 0.12,
                    'cross_decay': 0.04,
                    'adaptation_cap_delta': 0.34,
                    'innate_pull_rate': 0.03
                },
                'competition': {
                    'competition_probability': 0.04,
                    'resource_transfer_rate': 0.08,
                    'population_pressure_factor': 0.25,
                    'battle_casualty_scale': 0.08,
                    'battle_injury_scale': 0.18
                }
            }
        }
    }
    
    @classmethod
    def get_preset_names(cls) -> list:
        """获取所有预设名称"""
        return list(cls.PRESETS.keys())
    
    @classmethod
    def get_preset_description(cls, name: str) -> str:
        """获取预设描述"""
        preset = cls.PRESETS.get(name, {})
        return preset.get('description', '无描述')
    
    @classmethod
    def create_simulation_config(cls, preset_name: str = 'default') -> SimulationConfig:
        """根据预设创建模拟配置"""
        preset = cls.PRESETS.get(preset_name, cls.PRESETS['default'])
        config_data = preset['config']
        return SimulationConfig(**config_data)
    
    @classmethod
    def get_mechanism_configs(cls, preset_name: str = 'default') -> Dict[str, Dict]:
        """获取机制配置"""
        preset = cls.PRESETS.get(preset_name, cls.PRESETS['default'])
        return preset['mechanisms']
    
    @classmethod
    def create_custom_preset(cls, name: str, base_preset: str, 
                            config_overrides: Dict[str, Any],
                            mechanism_overrides: Dict[str, Dict[str, Any]]) -> str:
        """创建自定义预设"""
        base = deepcopy(cls.PRESETS.get(base_preset, cls.PRESETS['default']))
        
        # 应用覆盖
        for key, value in config_overrides.items():
            base['config'][key] = value
        
        for mech_name, mech_params in mechanism_overrides.items():
            if mech_name in base['mechanisms']:
                base['mechanisms'][mech_name].update(mech_params)
        
        base['description'] = f"自定义预设 (基于 {base_preset})"
        
        cls.PRESETS[name] = base
        return name
