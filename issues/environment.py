import cherrypy, os.path, threading

_thread_local_data = threading.local()

def compute_config_path(root):
    config_path = os.path.join(root, 'config', 'main.ini')
    return config_path

def load_config(root):
    config_path = compute_config_path(root)
    if os.path.exists(config_path):
        cherrypy.config.update(config_path)

def setup(root):
    import main_controller
    config_path = compute_config_path(root)
    kwargs = dict()
    if os.path.exists(config_path):
        kwargs['config'] = config_path
    cherrypy.tree.mount(main_controller.MainController(), '/', **kwargs)

def get_proxy():
    global _thread_local_data
    
    try:
        proxy = _thread_local_data.proxy
    except AttributeError:
        import proxy as proxy_module
        
        if cherrypy.config['local.cache.enabled']:
            cls = proxy_module.CachingProxy
        else:
            cls = proxy_module.Proxy
        _thread_local_data.proxy = proxy = cls()
    return proxy
