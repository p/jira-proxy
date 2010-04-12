import cherrypy, os.path, threading

_thread_local_data = threading.local()
fs_root = None

def compute_config_path(config_file):
    config_path = os.path.join(fs_root, 'config', config_file)
    return config_path

def load_config(root):
    global fs_root
    fs_root = root
    add_config('main.ini')

def add_config(config_file):
    config_path = compute_config_path(config_file)
    if os.path.exists(config_path):
        cherrypy.config.update(config_path)

def setup(root):
    global fs_root
    fs_root = root
    import main_controller
    config_path = compute_config_path('main.ini')
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
