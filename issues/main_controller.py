import cherrypy

import environment

class MainController:
    @cherrypy.expose
    def default(self, *args, **kwargs):
        self._munge_params()
        return self._proxy_content()
    
    def _proxy(self, **kwargs):
        response = environment.get_proxy().perform_and_propagate(**kwargs)
        return response
    
    def _proxy_content(self, **kwargs):
        response = self._proxy(**kwargs)
        return response.content
    
    def _munge_params(self):
        params = cherrypy.request.params
        proxy_host = cherrypy.request.headers['host']
        remote_host = cherrypy.config['remote.host']
        prefix = 'http://'
        search = prefix + proxy_host
        replace = prefix + remote_host
        for key, value in params.items():
            if value.startswith(search):
                value = replace + value[len(search):]
                params[key] = value
