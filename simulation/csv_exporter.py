"""
CSV数据导出模块 - 支持运行时数据导出
"""
import csv
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class CSVExporter:
    """CSV导出器 - 实时导出模拟数据"""
    
    def __init__(self, output_dir: str = "./csv_data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 文件句柄缓存
        self._file_handles: Dict[str, object] = {}
        self._csv_writers: Dict[str, object] = {}
        
        # 初始化标志
        self._initialized = False
        
    def initialize(self, simulation_id: str = None):
        """初始化导出文件"""
        if simulation_id is None:
            simulation_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        self.simulation_id = simulation_id
        self.run_dir = self.output_dir / simulation_id
        self.run_dir.mkdir(exist_ok=True)
        
        # 创建各个数据文件
        self._create_files()
        self._initialized = True
        
        print(f"CSV导出目录: {self.run_dir}")
        return self.run_dir
    
    def _create_files(self):
        """创建CSV文件并写入表头"""
        files_config = {
            'population.csv': [
                'month', 'tribe_id', 'tribe_type', 'population', 
                'male_count', 'female_count', 'hunters', 'gatherers',
                'pregnant_females', 'births_this_month', 'deaths_this_month'
            ],
            'resources.csv': [
                'month', 'tribe_id', 'tribe_type', 'total_resources',
                'food_meat', 'food_plant', 'productive_capacity', 'violence_capacity'
            ],
            'individuals.csv': [
                'month', 'tribe_id', 'individual_id', 'gender', 'age',
                'strength', 'intelligence', 'health', 'resources',
                'activity', 'is_pregnant', 'pregnancy_months'
            ],
            'events.csv': [
                'month', 'event_type', 'tribe_id', 'details', 'timestamp'
            ],
            'summary.csv': [
                'month', 'total_population', 'total_resources',
                'male_stronger_pop', 'female_stronger_pop', 'equal_pop',
                'total_births', 'total_deaths'
            ]
        }
        
        for filename, headers in files_config.items():
            filepath = self.run_dir / filename
            f = open(filepath, 'w', newline='', encoding='utf-8')
            writer = csv.writer(f)
            writer.writerow(headers)
            
            self._file_handles[filename] = f
            self._csv_writers[filename] = writer
    
    def export_monthly_data(self, month: int, tribes: Dict, monthly_events: Dict):
        """导出月度数据"""
        if not self._initialized:
            return
        
        # 导出人口数据
        self._export_population(month, tribes, monthly_events)
        
        # 导出资源数据
        self._export_resources(month, tribes)
        
        # 导出摘要数据
        self._export_summary(month, tribes, monthly_events)
        
        # 刷新缓冲区
        self._flush()
    
    def _export_population(self, month: int, tribes: Dict, events: Dict):
        """导出人口数据"""
        writer = self._csv_writers['population.csv']
        
        for tid, tribe in tribes.items():
            pregnant = sum(1 for ind in tribe.individuals.values() 
                          if ind.is_alive and ind.gender.name == 'FEMALE' and ind.is_pregnant)
            
            writer.writerow([
                month,
                tid,
                tribe.strength_relation.name,
                tribe.population,
                tribe.male_count,
                tribe.female_count,
                len(tribe.hunters),
                len(tribe.gatherers),
                pregnant,
                events.get('births', {}).get(tid, 0),
                events.get('deaths', {}).get(tid, 0)
            ])
    
    def _export_resources(self, month: int, tribes: Dict):
        """导出资源数据"""
        writer = self._csv_writers['resources.csv']
        
        for tid, tribe in tribes.items():
            writer.writerow([
                month,
                tid,
                tribe.strength_relation.name,
                tribe.total_resources,
                tribe.food_meat,
                tribe.food_plant,
                tribe.productive_capacity,
                tribe.violence_capacity
            ])
    
    def _export_summary(self, month: int, tribes: Dict, events: Dict):
        """导出摘要数据"""
        writer = self._csv_writers['summary.csv']
        
        total_pop = sum(t.population for t in tribes.values())
        total_res = sum(t.total_resources for t in tribes.values())
        
        pops_by_type = {'MALE_STRONGER': 0, 'FEMALE_STRONGER': 0, 'EQUAL': 0}
        for tribe in tribes.values():
            pops_by_type[tribe.strength_relation.name] = tribe.population
        
        total_births = sum(events.get('births', {}).values())
        total_deaths = sum(events.get('deaths', {}).values())
        
        writer.writerow([
            month, total_pop, total_res,
            pops_by_type['MALE_STRONGER'],
            pops_by_type['FEMALE_STRONGER'],
            pops_by_type['EQUAL'],
            total_births, total_deaths
        ])
    
    def export_individuals(self, month: int, tribes: Dict, sample_size: int = 50):
        """导出个体样本数据（用于详细分析）"""
        if not self._initialized:
            return
        
        writer = self._csv_writers['individuals.csv']
        
        for tid, tribe in tribes.items():
            # 只导出存活个体样本
            alive = [ind for ind in tribe.individuals.values() if ind.is_alive]
            
            # 如果个体太多，随机采样
            if len(alive) > sample_size:
                import random
                alive = random.sample(alive, sample_size)
            
            for ind in alive:
                writer.writerow([
                    month, tid, ind.id, ind.gender.name,
                    round(ind.age, 1),
                    round(ind.strength, 2),
                    round(ind.intelligence, 2),
                    round(ind.health, 2),
                    round(ind.resources, 2),
                    ind.assigned_activity.name if ind.assigned_activity else 'NONE',
                    1 if ind.is_pregnant else 0,
                    ind.pregnancy_months
                ])
    
    def log_event(self, month: int, event_type: str, tribe_id: int, details: str):
        """记录事件"""
        if not self._initialized:
            return
        
        writer = self._csv_writers['events.csv']
        writer.writerow([
            month, event_type, tribe_id, details,
            datetime.now().isoformat()
        ])
    
    def _flush(self):
        """刷新所有文件缓冲区"""
        for f in self._file_handles.values():
            f.flush()
    
    def close(self):
        """关闭所有文件"""
        for f in self._file_handles.values():
            f.close()
        self._file_handles.clear()
        self._csv_writers.clear()
        self._initialized = False
    
    def get_csv_paths(self) -> Dict[str, Path]:
        """获取所有CSV文件路径"""
        if not self._initialized:
            return {}
        
        return {
            name: self.run_dir / name 
            for name in self._file_handles.keys()
        }
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
