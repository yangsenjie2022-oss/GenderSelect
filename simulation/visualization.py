"""
可视化模块（能力驱动版本）
"""
from typing import Dict
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 非交互式后端
import numpy as np
from pathlib import Path

from .simulator import SimulationState


class SimulationVisualizer:
    """模拟结果可视化器"""
    
    def __init__(self, output_dir: str = "./output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def _tribe_label(self, tid: int) -> str:
        return f"Tribe {tid}"

    def _history_tribe_ids(self, state: SimulationState):
        ids = set(state.tribes.keys())
        for h in state.history:
            ids.update(h.get('tribes', {}).keys())
        return sorted(ids)
    
    def plot_population_dynamics(self, state: SimulationState, save: bool = True, 
                                  filename: str = "population_dynamics.png"):
        """绘制人口与受伤动态"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Population and Injury Dynamics', fontsize=14, fontweight='bold')
        history_data = state.history if state.history else []
        ax1, ax2, ax3, ax4 = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]

        if history_data:
            months = [h['month'] for h in history_data]
            tribe_ids = sorted(state.tribes.keys())
            for tid in tribe_ids:
                pops = [h['tribes'].get(tid, {}).get('population', 0) for h in history_data]
                ax1.plot(months, pops, linewidth=2, label=self._tribe_label(tid))

            total_pop = [sum(t['population'] for t in h['tribes'].values()) for h in history_data]
            total_inj = [sum(t.get('injured_count', 0) for t in h['tribes'].values()) for h in history_data]
            inj_ratio = [(i / p if p > 0 else 0) for i, p in zip(total_inj, total_pop)]
            ax2.plot(months, inj_ratio, color='#B33A3A', linewidth=2.5)

        ax1.set_xlabel('Month')
        ax1.set_ylabel('Population')
        ax1.set_title('Population by Tribe')
        ax1.grid(True, alpha=0.3)
        if ax1.get_legend_handles_labels()[0]:
            ax1.legend()

        ax2.set_xlabel('Month')
        ax2.set_ylabel('Injury Ratio')
        ax2.set_title('Global Injury Ratio Over Time')
        ax2.set_ylim(0, 1)
        ax2.grid(True, alpha=0.3)

        tribe_ids = sorted(state.tribes.keys())
        x = np.arange(len(tribe_ids))
        births = [state.tribes[tid].birth_count for tid in tribe_ids]
        deaths = [state.tribes[tid].death_count for tid in tribe_ids]
        width = 0.35
        ax3.bar(x - width / 2, births, width, label='Births', alpha=0.85)
        ax3.bar(x + width / 2, deaths, width, label='Deaths', alpha=0.6)
        ax3.set_xticks(x)
        ax3.set_xticklabels([self._tribe_label(tid) for tid in tribe_ids], rotation=20)
        ax3.set_title('Births vs Deaths by Tribe')
        ax3.grid(True, alpha=0.3, axis='y')
        ax3.legend()

        if tribe_ids:
            pops = [state.tribes[tid].population for tid in tribe_ids]
            ax4.pie(pops, labels=[self._tribe_label(tid) for tid in tribe_ids], autopct='%1.1f%%', startangle=90)
        ax4.set_title('Final Population Share')
        
        plt.tight_layout()
        
        if save:
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            print(f"图表已保存: {filepath}")
        
        return fig
    
    def plot_resource_analysis(self, state: SimulationState, save: bool = True,
                                filename: str = "resource_analysis.png"):
        """绘制资源、能力与受伤分析图"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Resource, Capability, and Injury Analysis', fontsize=14, fontweight='bold')
        
        history_data = state.history if state.history else []
        ax1, ax2, ax3, ax4 = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]

        if history_data:
            months = [h['month'] for h in history_data]
            tribe_ids = sorted(state.tribes.keys())
            for tid in tribe_ids:
                res = [h['tribes'].get(tid, {}).get('resources', 0.0) for h in history_data]
                ax1.plot(months, res, linewidth=2, label=self._tribe_label(tid))
        ax1.set_xlabel('Month')
        ax1.set_ylabel('Resources')
        ax1.set_title('Resource Dynamics by Tribe')
        ax1.grid(True, alpha=0.3)
        if ax1.get_legend_handles_labels()[0]:
            ax1.legend()

        for tid, tribe in state.tribes.items():
            if tribe.population > 0:
                ax2.scatter(
                    tribe.productive_capacity, tribe.violence_capacity,
                    s=max(30, tribe.population * 4),
                    alpha=0.7, edgecolors='black', label=self._tribe_label(tid)
                )
        ax2.set_xlabel('Productive Capacity')
        ax2.set_ylabel('Violence Capacity')
        ax2.set_title('Capability Comparison')
        ax2.grid(True, alpha=0.3)
        if ax2.get_legend_handles_labels()[0]:
            ax2.legend()

        labels = []
        hunter_ratios = []
        injured_ratios = []
        for tid, tribe in state.tribes.items():
            if tribe.population <= 0:
                continue
            labels.append(self._tribe_label(tid))
            hunter_ratios.append(len(tribe.hunters) / tribe.population)
            injured_ratios.append(tribe.injured_count / tribe.population)
        x = np.arange(len(labels))
        width = 0.35
        ax3.bar(x - width / 2, hunter_ratios, width, label='Hunter Ratio', alpha=0.85)
        ax3.bar(x + width / 2, injured_ratios, width, label='Injured Ratio', alpha=0.75)
        ax3.set_xticks(x)
        ax3.set_xticklabels(labels, rotation=20)
        ax3.set_ylim(0, 1)
        ax3.set_title('Hunter vs Injury Ratios')
        ax3.grid(True, alpha=0.3, axis='y')
        ax3.legend()

        survival_rates = []
        s_labels = []
        for tid, tribe in state.tribes.items():
            if tribe.birth_count + tribe.population > 0:
                survival_rates.append(tribe.population / (tribe.birth_count + tribe.population) * 100)
                s_labels.append(self._tribe_label(tid))
        if survival_rates:
            bars = ax4.bar(s_labels, survival_rates, alpha=0.85, edgecolor='black')
            ax4.set_ylabel('Survival Rate (%)')
            ax4.set_title('Survival Rate by Tribe')
            ax4.grid(True, alpha=0.3, axis='y')
            for bar, rate in zip(bars, survival_rates):
                ax4.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{rate:.1f}%', ha='center', va='bottom')
        
        plt.tight_layout()
        
        if save:
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            print(f"图表已保存: {filepath}")
        
        return fig
    
    def plot_comprehensive_report(self, state: SimulationState, save: bool = True,
                                   filename: str = "comprehensive_report.png"):
        """绘制综合报告（复用核心图）"""
        fig = plt.figure(figsize=(16, 12))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
        
        fig.suptitle('Ability-Based Evolution Simulation: Comprehensive Report', 
                     fontsize=16, fontweight='bold', y=0.98)
        
        ax_pop = fig.add_subplot(gs[0, :2])
        history_data = state.history if state.history else []
        
        if history_data:
            months = [h['month'] for h in history_data]
            for tid in sorted(state.tribes.keys()):
                pop = [h['tribes'].get(tid, {}).get('population', 0) for h in history_data]
                ax_pop.plot(months, pop, linewidth=2.5, label=self._tribe_label(tid))
        
        ax_pop.set_xlabel('Month', fontsize=11)
        ax_pop.set_ylabel('Population', fontsize=11)
        ax_pop.set_title('Population Dynamics', fontsize=12, fontweight='bold')
        if ax_pop.get_legend_handles_labels()[0]:
            ax_pop.legend(fontsize=10)
        ax_pop.grid(True, alpha=0.3)
        
        ax_text = fig.add_subplot(gs[0, 2])
        ax_text.axis('off')
        
        text_content = "Final Results\n" + "="*25 + "\n\n"
        for tid, tribe in state.tribes.items():
            text_content += f"{self._tribe_label(tid)}:\n"
            text_content += f"  Population: {tribe.population}\n"
            text_content += f"  Births: {tribe.birth_count}\n"
            text_content += f"  Deaths: {tribe.death_count}\n"
            text_content += f"  Injured: {tribe.injured_count}\n"
            if tribe.birth_count > 0:
                survival = tribe.population / (tribe.birth_count + tribe.population) * 100
                text_content += f"  Survival: {survival:.1f}%\n"
            text_content += "\n"
        
        ax_text.text(0.1, 0.5, text_content, transform=ax_text.transAxes,
                    fontsize=10, verticalalignment='center',
                    fontfamily='monospace',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
        
        ax_res = fig.add_subplot(gs[1, 0])
        if history_data:
            months = [h['month'] for h in history_data]
            for tid in sorted(state.tribes.keys()):
                res = [h['tribes'].get(tid, {}).get('resources', 0.0) for h in history_data]
                ax_res.plot(months, res, linewidth=2, label=self._tribe_label(tid))
        
        ax_res.set_xlabel('Month')
        ax_res.set_ylabel('Resources')
        ax_res.set_title('Resource Dynamics')
        if ax_res.get_legend_handles_labels()[0]:
            ax_res.legend(fontsize=8)
        ax_res.grid(True, alpha=0.3)
        
        ax_cap = fig.add_subplot(gs[1, 1])
        for tid, tribe in state.tribes.items():
            if tribe.population > 0:
                ax_cap.scatter(tribe.productive_capacity, tribe.violence_capacity,
                              s=tribe.population * 4,
                              alpha=0.7,
                              edgecolors='black',
                              label=self._tribe_label(tid))
        
        ax_cap.set_xlabel('Productivity')
        ax_cap.set_ylabel('Violence Capacity')
        ax_cap.set_title('Tribe Capabilities')
        ax_cap.legend(fontsize=8)
        ax_cap.grid(True, alpha=0.3)
        
        ax_pie = fig.add_subplot(gs[1, 2])
        populations = []
        labels = []
        
        for tid, tribe in state.tribes.items():
            if tribe.population > 0:
                populations.append(tribe.population)
                labels.append(self._tribe_label(tid))
        
        if populations:
            ax_pie.pie(populations, labels=labels, autopct='%1.1f%%', startangle=90)
            ax_pie.set_title('Population Distribution')
        
        ax_table = fig.add_subplot(gs[2, :])
        ax_table.axis('off')
        
        table_data = [['Tribe', 'Population', 'Male/Female', 'Hunters', 'Injured', 'Resources', 'Survival Rate']]
        
        for tid, tribe in state.tribes.items():
            if tribe.birth_count + tribe.population > 0:
                survival = tribe.population / (tribe.birth_count + tribe.population) * 100
            else:
                survival = 0
            
            row = [
                self._tribe_label(tid),
                str(tribe.population),
                f"{tribe.male_count}/{tribe.female_count}",
                f"{len(tribe.hunters)} ({len(tribe.hunters)/max(1,tribe.population)*100:.1f}%)",
                f"{tribe.injured_count} ({tribe.injured_count/max(1,tribe.population)*100:.1f}%)",
                f"{tribe.total_resources:.1f}",
                f"{survival:.1f}%"
            ]
            table_data.append(row)
        
        if len(table_data) > 1:
            table = ax_table.table(cellText=table_data[1:], colLabels=table_data[0],
                                  cellLoc='center', loc='center',
                                  colColours=['#4472C4'] * 7)
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            table.scale(1, 2)
            
            # 设置表头颜色
            for i in range(7):
                table[(0, i)].set_text_props(color='white', fontweight='bold')
            
            ax_table.set_title('Detailed Statistics', fontsize=12, fontweight='bold', pad=20)
        else:
            ax_table.text(0.5, 0.5, 'No surviving tribes', ha='center', va='center', fontsize=14)
        
        if save:
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            print(f"综合报告已保存: {filepath}")
        
        return fig
    
    def plot_evolution_trajectory(self, state: SimulationState, save: bool = True,
                                   filename: str = "evolution_trajectory.png"):
        """绘制进化轨迹（能力驱动版本）"""
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle('Evolutionary Trajectory: Tribe Competition and Injury Burden', 
                     fontsize=14, fontweight='bold')
        
        # 从history提取数据
        if not state.history:
            print("没有历史数据可绘制")
            return fig
        
        months = [h['month'] for h in state.history]
        n_months = len(months)
        
        ax1 = axes[0]
        total_pop_by_month = [sum(t['population'] for t in h['tribes'].values()) for h in state.history]
        for tid in sorted(state.tribes.keys()):
            pop = [h['tribes'].get(tid, {}).get('population', 0) for h in state.history]
            ratio = [p / total if total > 0 else 0 for p, total in zip(pop, total_pop_by_month)]
            ax1.plot(months, ratio, linewidth=2.5, label=self._tribe_label(tid))
        
        ax1.set_xlabel('Month')
        ax1.set_ylabel('Population Proportion')
        ax1.set_title('Population Share by Tribe')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(0, 1)
        
        ax2 = axes[1]
        injury_ratio = []
        for h in state.history:
            total_pop = sum(t.get('population', 0) for t in h['tribes'].values())
            total_inj = sum(t.get('injured_count', 0) for t in h['tribes'].values())
            injury_ratio.append(total_inj / total_pop if total_pop > 0 else 0)
        cumulative_burden = np.cumsum(injury_ratio)
        ax2.plot(months, cumulative_burden, linewidth=2.5, color='#B33A3A', label='Cumulative Injury Burden')
        
        ax2.set_xlabel('Month')
        ax2.set_ylabel('Cumulative Injury Burden')
        ax2.set_title('Long-term Injury Burden')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save:
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            print(f"进化轨迹图已保存: {filepath}")
        
        return fig

    def plot_gender_strength_and_rates(
        self,
        state: SimulationState,
        save: bool = True,
        filename: str = "gender_strength_and_rates.png"
    ):
        """绘制雄雌平均力量、总出生死亡率、以及分性别率曲线"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Gender Strength and Birth/Death Rates', fontsize=14, fontweight='bold')

        if not state.history:
            print("没有历史数据可绘制")
            return fig

        months = [h['month'] for h in state.history]

        global_male_strength = []
        global_female_strength = []
        total_birth_rate = []
        total_death_rate = []
        male_birth_rate = []
        female_birth_rate = []
        male_death_rate = []
        female_death_rate = []

        for h in state.history:
            tribes_map = h.get('tribes', {})
            births = h.get('births', {})
            deaths = h.get('deaths', {})
            births_male = h.get('births_male', {})
            births_female = h.get('births_female', {})
            deaths_male = h.get('deaths_male', {})
            deaths_female = h.get('deaths_female', {})

            male_count_now = sum(t.get('male_count', 0) for t in tribes_map.values())
            female_count_now = sum(t.get('female_count', 0) for t in tribes_map.values())

            weighted_male_strength = sum(
                t.get('avg_male_strength', 0.0) * t.get('male_count', 0) for t in tribes_map.values()
            )
            weighted_female_strength = sum(
                t.get('avg_female_strength', 0.0) * t.get('female_count', 0) for t in tribes_map.values()
            )
            global_male_strength.append(weighted_male_strength / male_count_now if male_count_now > 0 else 0.0)
            global_female_strength.append(weighted_female_strength / female_count_now if female_count_now > 0 else 0.0)

            start_pop = 0
            start_male = 0
            start_female = 0
            total_birth = 0
            total_death = 0
            total_birth_male = 0
            total_birth_female = 0
            total_death_male = 0
            total_death_female = 0

            for tid, t in tribes_map.items():
                b = births.get(tid, 0)
                d = deaths.get(tid, 0)
                bm = births_male.get(tid, 0)
                bf = births_female.get(tid, 0)
                dm = deaths_male.get(tid, 0)
                df = deaths_female.get(tid, 0)

                pop_now = t.get('population', 0)
                male_now = t.get('male_count', 0)
                female_now = t.get('female_count', 0)

                pop_start = max(0, pop_now - b + d)
                male_start = max(0, male_now - bm + dm)
                female_start = max(0, female_now - bf + df)

                start_pop += pop_start
                start_male += male_start
                start_female += female_start

                total_birth += b
                total_death += d
                total_birth_male += bm
                total_birth_female += bf
                total_death_male += dm
                total_death_female += df

            total_birth_rate.append(total_birth / start_pop if start_pop > 0 else 0.0)
            total_death_rate.append(total_death / start_pop if start_pop > 0 else 0.0)
            male_birth_rate.append(total_birth_male / start_male if start_male > 0 else 0.0)
            female_birth_rate.append(total_birth_female / start_female if start_female > 0 else 0.0)
            male_death_rate.append(total_death_male / start_male if start_male > 0 else 0.0)
            female_death_rate.append(total_death_female / start_female if start_female > 0 else 0.0)

        ax1, ax2, ax3, ax4 = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]
        ax1.plot(months, global_male_strength, label='Male Avg Strength', linewidth=2.3, color='#1f77b4')
        ax1.plot(months, global_female_strength, label='Female Avg Strength', linewidth=2.3, color='#d62728')
        ax1.set_title('Male vs Female Average Strength (Monthly)')
        ax1.set_xlabel('Month')
        ax1.set_ylabel('Strength')
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        ax2.plot(months, total_birth_rate, label='Total Birth Rate', linewidth=2.3, color='#2ca02c')
        ax2.plot(months, total_death_rate, label='Total Death Rate', linewidth=2.3, color='#9467bd')
        ax2.set_title('Total Birth/Death Rate (Monthly)')
        ax2.set_xlabel('Month')
        ax2.set_ylabel('Rate')
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        ax3.plot(months, male_birth_rate, label='Male Birth Rate', linewidth=2.0, color='#17becf')
        ax3.plot(months, female_birth_rate, label='Female Birth Rate', linewidth=2.0, color='#ff7f0e')
        ax3.set_title('Gender-specific Birth Rates')
        ax3.set_xlabel('Month')
        ax3.set_ylabel('Rate')
        ax3.grid(True, alpha=0.3)
        ax3.legend()

        ax4.plot(months, male_death_rate, label='Male Death Rate', linewidth=2.0, color='#8c564b')
        ax4.plot(months, female_death_rate, label='Female Death Rate', linewidth=2.0, color='#e377c2')
        ax4.set_title('Gender-specific Death Rates')
        ax4.set_xlabel('Month')
        ax4.set_ylabel('Rate')
        ax4.grid(True, alpha=0.3)
        ax4.legend()

        plt.tight_layout()

        if save:
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            print(f"图表已保存: {filepath}")

        return fig

    def plot_strength_ratio_comparison(
        self,
        state: SimulationState,
        save: bool = True,
        filename: str = "strength_ratio_comparison.png"
    ):
        """绘制雌雄力量比例与部落人数、生产力对比"""
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle('Strength Ratio vs Population/Productivity', fontsize=14, fontweight='bold')

        ratios = []
        populations = []
        productivities = []
        labels = []

        for tid, tribe in state.tribes.items():
            if tribe.population <= 0 or tribe.avg_female_strength <= 0:
                continue
            ratio = tribe.avg_male_strength / tribe.avg_female_strength
            ratios.append(ratio)
            populations.append(tribe.population)
            productivities.append(tribe.productive_capacity)
            labels.append(self._tribe_label(tid))

        ax1, ax2 = axes[0], axes[1]
        if ratios:
            ax1.scatter(ratios, populations, s=80, alpha=0.8, edgecolors='black')
            ax2.scatter(ratios, productivities, s=80, alpha=0.8, edgecolors='black')
            for x, y, lbl in zip(ratios, populations, labels):
                ax1.annotate(lbl, (x, y), textcoords="offset points", xytext=(5, 5), fontsize=8)
            for x, y, lbl in zip(ratios, productivities, labels):
                ax2.annotate(lbl, (x, y), textcoords="offset points", xytext=(5, 5), fontsize=8)

        ax1.set_xlabel('Male/Female Strength Ratio')
        ax1.set_ylabel('Population')
        ax1.set_title('Strength Ratio vs Population')
        ax1.grid(True, alpha=0.3)

        ax2.set_xlabel('Male/Female Strength Ratio')
        ax2.set_ylabel('Productive Capacity')
        ax2.set_title('Strength Ratio vs Productivity')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if save:
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            print(f"图表已保存: {filepath}")

        return fig
    
    def generate_all_plots(self, state: SimulationState):
        """生成所有图表"""
        print("\n生成可视化图表...")
        
        self.plot_population_dynamics(state)
        self.plot_resource_analysis(state)
        self.plot_gender_strength_and_rates(state)
        self.plot_strength_ratio_comparison(state)
        self.plot_comprehensive_report(state)
        self.plot_evolution_trajectory(state)
        
        print(f"所有图表已保存到: {self.output_dir}")
