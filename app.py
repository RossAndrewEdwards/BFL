import sys
import types
import src.app

class ProxyModule(types.ModuleType):
    def __getattr__(self, name):
        return getattr(src.app, name)
        
    def __setattr__(self, name, value):
        setattr(src.app, name, value)

    def __dir__(self):
        return dir(src.app)

# Expose all public symbols from src.app for star imports
__all__ = [k for k in dir(src.app) if not k.startswith('_')]

# Swap this module's class to the proxy class
sys.modules[__name__].__class__ = ProxyModule
