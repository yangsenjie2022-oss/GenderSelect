"""
依赖注入容器 - 核心基础设施
支持配置的热更新和模块替换
"""
from typing import Dict, Type, Any, Callable, Optional
import json
import pickle
import os
from dataclasses import dataclass, asdict, is_dataclass


class DIContainer:
    """依赖注入容器"""
    
    def __init__(self):
        self._registrations: Dict[str, Any] = {}
        self._singletons: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._configs: Dict[str, Any] = {}
    
    def register_instance(self, interface_name: str, instance: Any):
        """注册单例实例"""
        self._singletons[interface_name] = instance
        return self
    
    def register_factory(self, interface_name: str, factory: Callable, singleton: bool = False):
        """注册工厂函数"""
        self._factories[interface_name] = {'factory': factory, 'singleton': singleton}
        return self
    
    def register_class(self, interface_name: str, cls: Type, singleton: bool = False):
        """注册类，自动解析构造函数依赖"""
        def factory(container: 'DIContainer'):
            # 获取构造函数参数
            import inspect
            sig = inspect.signature(cls.__init__)
            params = list(sig.parameters.items())[1:]  # 跳过self
            
            kwargs = {}
            for name, param in params:
                if param.default != inspect.Parameter.empty:
                    continue
                # 尝试从容器获取依赖
                dep = container.resolve(name, optional=True)
                if dep is not None:
                    kwargs[name] = dep
            
            return cls(**kwargs)
        
        self._factories[interface_name] = {
            'factory': factory, 
            'singleton': singleton,
            'class': cls
        }
        return self
    
    def register_config(self, key: str, value: Any):
        """注册配置项"""
        self._configs[key] = value
        return self
    
    def resolve(self, interface_name: str, optional: bool = False) -> Any:
        """解析依赖"""
        # 1. 检查已存在的单例
        if interface_name in self._singletons:
            return self._singletons[interface_name]
        
        # 2. 检查工厂
        if interface_name in self._factories:
            factory_info = self._factories[interface_name]
            instance = factory_info['factory'](self)
            if factory_info['singleton']:
                self._singletons[interface_name] = instance
            return instance
        
        # 3. 检查配置
        if interface_name in self._configs:
            return self._configs[interface_name]
        
        if optional:
            return None
        
        raise KeyError(f"未注册的依赖: {interface_name}")
    
    def resolve_config(self, key: str, default: Any = None) -> Any:
        """解析配置项"""
        keys = key.split('.')
        value = self._configs
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def update_config(self, key: str, value: Any):
        """动态更新配置"""
        keys = key.split('.')
        config = self._configs
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
    
    def save_state(self, filepath: str):
        """保存容器状态（包括配置和单例状态）"""
        state = {
            'configs': self._configs,
            'singletons': {}
        }
        # 只保存可序列化的单例
        for name, instance in self._singletons.items():
            if hasattr(instance, '__getstate__'):
                state['singletons'][name] = instance.__getstate__()
            elif hasattr(instance, '__dict__'):
                try:
                    pickle.dumps(instance)
                    state['singletons'][name] = instance
                except:
                    pass
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            pickle.dump(state, f)
        print(f"状态已保存到: {filepath}")
    
    def load_state(self, filepath: str):
        """加载容器状态"""
        if not os.path.exists(filepath):
            print(f"存档不存在: {filepath}")
            return False
        
        with open(filepath, 'rb') as f:
            state = pickle.load(f)
        
        self._configs.update(state.get('configs', {}))
        
        # 恢复单例状态
        for name, saved_state in state.get('singletons', {}).items():
            if name in self._factories:
                # 重新创建实例
                instance = self.resolve(name)
                if hasattr(instance, '__setstate__'):
                    instance.__setstate__(saved_state)
                elif isinstance(saved_state, dict) and hasattr(instance, '__dict__'):
                    instance.__dict__.update(saved_state)
        
        print(f"状态已从 {filepath} 加载")
        return True


# 全局容器实例
_container: Optional[DIContainer] = None


def get_container() -> DIContainer:
    """获取全局容器实例"""
    global _container
    if _container is None:
        _container = DIContainer()
    return _container


def reset_container():
    """重置容器（用于测试）"""
    global _container
    _container = DIContainer()


def inject(interface_name: str):
    """依赖注入装饰器"""
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            if interface_name not in kwargs:
                kwargs[interface_name] = get_container().resolve(interface_name)
            return func(*args, **kwargs)
        return wrapper
    return decorator
