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
    
    def _replace_host(self, search_host, replace_host):
        params = cherrypy.request.params
        prefix = 'http://'
        search = prefix + search_host
        replace = prefix + replace_host
        for key, value in params.items():
            # todo: check if non-strings contain host
            if isinstance(value, basestring) and value.startswith(search):
                value = replace + value[len(search):]
                params[key] = value
    
    def _munge_params(self):
        self._replace_host(cherrypy.request.headers['host'], cherrypy.config['remote.host'])
        local_host = cherrypy.config.get('local.host')
        if local_host:
            self._replace_host(local_host, cherrypy.config['remote.host'])
    
    # Googlebot gets its nose in everywhere.
    # Save us the aggravation of putting up with it.
    # We don't have any original content anyway.
    @cherrypy.expose
    def robots_txt(self):
        cherrypy.response.headers['content-type'] = 'text/plain'
        return "User-Agent: *\nDisallow: /\n"
    
    # We rewrite some useless urls to blank_page on varnish
    @cherrypy.expose
    def blank_page(self, *args, **kwargs):
        cherrypy.response.headers['content-type'] = 'text/plain'
        return None
