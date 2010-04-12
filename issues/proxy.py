import cherrypy, re, os.path, cPickle as pickle, time, calendar

from base_proxy import BaseProxy
import tools.hashlib_shortcuts, tools.file

def expires_to_timestamp(expires):
    return calendar.timegm(time.strptime(expires, '%a, %d %b %Y %H:%M:%S %Z'))

class Proxy(BaseProxy):
    default_remote_host = cherrypy.config['remote.host']
    
    reverse_host_map = {
        cherrypy.config['remote.host']: '',
    }
    
    def __init__(self):
        BaseProxy.__init__(self)
        
        self.html_comment_re = re.compile(r'<!--.*?-->', re.S)
        self.html_script_re = re.compile(r'<script.*?</script>', re.S)
    
    def perform(self, **kwargs):
        BaseProxy.perform(self, **kwargs)
        
        self._adjust_cache_directives()
        self._adjust_host_in_links()
    
    def _adjust_cache_directives(self):
        r = self._remote_response
        
        # kill no-cache and no-store directives.
        # note whether response was marked public; only public responses are saved to disk
        r.public = False
        if r.headers.has_key('pragma'):
            value = r.headers['pragma']
            # xxx hack: multiple pragmas are theoretically possible, but unlikely
            if value == 'no-cache':
                del r.headers['pragma']
        if r.headers.has_key('cache-control'):
            value = r.headers['cache-control']
            parts = [part.strip() for part in value.split(',')]
            new_parts = [part for part in parts if part not in ['no-cache', 'no-store']]
            if len(parts) != len(new_parts):
                new_value = ', '.join(new_parts)
                r.headers['cache-control'] = new_value
            if 'public' in new_parts:
                r.public = True
        # kill past expiration dates
        if r.headers.has_key('expires'):
            expires_at = expires_to_timestamp(r.headers['expires'])
            if expires_at < time.time():
                del r.headers['expires']
        
    def _adjust_host_in_links(self):
        r = self._remote_response
        
        if r.headers['content-type'].lower().startswith('text/html'):
            content = r.content
            content = self.html_comment_re.sub('', content)
            search = cherrypy.config['remote.host']
            replace = cherrypy.request.headers.get('host') or self.__class__.default_remote_host
            content = content.replace(search, replace)
            #content = self.html_script_re.sub(lambda match: match.group(0).replace(search, replace), content)
            r.content = content

class ContentWrapper:
    def __init__(self, content):
        self.content = content

class CachingProxy(Proxy):
    def perform_and_propagate(self, **kwargs):
        self._setup_cache_variables()
        content = self._find_in_cache()
        if content is None:
            response = Proxy.perform_and_propagate(self, **kwargs)
            if not response.private:
                self._save_to_cache(response)
        else:
            response = ContentWrapper(content)
        return response
    
    def _setup_cache_variables(self):
        self.cache_absolute_path = self.cache_absolute_path_meta = None
        r = cherrypy.request
        if r.query_string:
            hashed_qs = tools.hashlib_shortcuts.md5_hexdigest(r.query_string)
            relative_path = r.path_info + '::' + hashed_qs
        else:
            relative_path = r.path_info
        if relative_path.find('..') >= 0:
            raise ValueError('Suspicious request relative path: %s' % relative_path)
        assert relative_path[0] == '/'
        relative_path = relative_path[1:]
        if relative_path:
            assert relative_path[0] != '/'
            self.cache_absolute_path = os.path.join(cherrypy.config['local.cache.dir'], relative_path)
            self.cache_absolute_path_meta = self.cache_absolute_path + '.meta'
    
    def _find_in_cache(self):
        if self.cache_absolute_path_meta is not None and os.path.exists(self.cache_absolute_path_meta):
            headers = pickle.loads(tools.file.read(self.cache_absolute_path_meta))
            expires = headers['x-expires-timestamp']
            now = time.time()
            if expires >= now:
                for key, value in headers.items():
                    cherrypy.response.headers[key] = value
                content = tools.file.read(self.cache_absolute_path)
                return content
    
    def _save_to_cache(self, response):
        if self.cache_absolute_path is None:
            return
        
        headers = response.headers
        expires_at = None
        if headers.has_key('cache-control'):
            cache_control = headers['cache-control']
            parts = [part.strip() for part in cache_control.split(',')]
            for part in parts:
                if part.startswith('max-age='):
                    age = int(part[8:])
                    expires_at = int(time.time()) + age
                    break
        if expires_at is None and headers.has_key('expires'):
            expires_at = expires_to_timestamp(headers['expires'])
        if expires_at is not None:
            headers['x-expires-timestamp'] = expires_at
            dir = os.path.dirname(self.cache_absolute_path)
            if not os.path.exists(dir):
                tools.file.safe_mkdirs(dir)
            tools.file.safe_write(self.cache_absolute_path, response.content)
            tools.file.safe_write(self.cache_absolute_path_meta, pickle.dumps(headers))
