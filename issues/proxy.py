import cherrypy, re, os.path, cPickle as pickle, time, calendar

from base_proxy import BaseProxy
import tools.hashlib_shortcuts, tools.file

def expires_to_timestamp(expires):
    try:
        # Expires: 0
        int(expires)
        return time.time()-86400
    except:
        return calendar.timegm(time.strptime(expires, '%a, %d %b %Y %H:%M:%S %Z'))

class Proxy(BaseProxy):
    default_remote_host = cherrypy.config['remote.host']
    
    reverse_host_map = {
        cherrypy.config['remote.host']: '',
    }
    
    adjust_host_in_content_types = ('text/html', 'application/xml', 'application/json')
    
    def __init__(self):
        BaseProxy.__init__(self)
        
        self.html_comment_re = re.compile(r'<!--.*?-->', re.S)
        self.html_script_re = re.compile(r'<script.*?</script>', re.S)
        
        # note: we use re.match which requires match from beginning
        self.public_paths_re = re.compile(r'/(s/|images/|favicon\.ico|rest/api/1\.0/(header-separator|dropdowns)($|\?))')
    
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
        
        content_type = r.headers['content-type'].lower()
        for check in self.__class__.adjust_host_in_content_types:
            if content_type.startswith(check):
                content = r.content
                content = self.html_comment_re.sub('', content)
                local_host = cherrypy.config.get('local.host')
                incoming_host = cherrypy.request.headers.get('host')
                search = cherrypy.config['remote.host']
                replace = local_host or incoming_host or self.__class__.default_remote_host
                content = content.replace(search, replace)
                if local_host:
                    content = content.replace(incoming_host, local_host)
                #content = self.html_script_re.sub(lambda match: match.group(0).replace(search, replace), content)
                r.content = content
                break
    
    def _collect_request_parameters(self, **kwargs):
        BaseProxy._collect_request_parameters(self, **kwargs)
        
        # jira puts hostname into self-referential links, and hostname comes from jira configuration.
        # in case of jira proxy-served pages, that hostname is wrong.
        # this means an http accelerator like varnish which does not edit response bodies
        # cannot serve usable pages when running on any host other than configured jira host.
        # in turn this means jira proxy must always be involved in proxying process.
        # running an accelerator on top of jira-proxy makes latency even worse, so to maintain
        # some semblance of sanity we have to do all transformations that varnish does.
        self._adjust_request()
    
    # header adjustments from varnish
    def _adjust_request(self):
        if self.public_paths_re.match(self._params.path):
            self._params.clear_cookies()
    
    def _issue_remote_request(self):
        BaseProxy._issue_remote_request(self)
        
        # see note in _collect_request_parameters.
        # do what should be done in varnish
        self._adjust_response()
    
    # header adjustments from varnish
    def _adjust_response(self):
        if self.public_paths_re.match(self._params.path):
            self._remote_response.clear_cookies()
            self._make_response_public()
            # be aggressive here since we don't get much traffic
            self._force_min_expiration(86400)
    
    def _make_response_public(self):
        h = self._remote_response.headers
        if h.has_key('cache-control'):
            cache_control = [part.strip() for part in h['cache-control'].split(',')]
            if 'private' in cache_control:
                # asked to make public a private response...
                # we strip cookies on public paths so we should be ok to ignore this
                cache_control.delete('private')
            if 'public' not in cache_control:
                cache_control.append('public')
            cache_control = ', '.join(cache_control)
        else:
            cache_control = 'public'
        h['cache-control'] = cache_control
    
    def _force_min_expiration(self, time_in_seconds):
        h = self._remote_response.headers
        expires_at = self._determine_response_expiration_time(self._remote_response)
        min_expires_at = int(time.time()) + time_in_seconds
        if expires_at is None or expires_at < min_expires_at:
            if h.has_key('cache-control'):
                cache_control = [part.strip() for part in h['cache-control'].split(',')]
                for part in cache_control:
                    if part.startswith('max-age='):
                        cache_control.remove(part)
                        break
            else:
                cache_control = []
            cache_control.append('max-age=%d' % time_in_seconds)
            h['cache-control'] = ', '.join(cache_control)
            if h.has_key('expires'):
                del h['expires']
    
    def _determine_response_expiration_time(self, response):
        h = response.headers
        expires_at = None
        # max-age takes precedence over expires
        if h.has_key('cache-control'):
            parts = [part.strip() for part in h['cache-control'].split(',')]
            for part in parts:
                if part.startswith('max-age='):
                    age = int(part[8:])
                    expires_at = int(time.time()) + age
                    break
        if expires_at is None and h.has_key('expires'):
            expires_at = expires_to_timestamp(h['expires'])
        return expires_at

class ContentWrapper:
    def __init__(self, content):
        self.content = content

class CachingProxy(Proxy):
    def perform_and_propagate(self, **kwargs):
        self._setup_cache_variables()
        content = self._find_in_cache()
        if content is None:
            response = Proxy.perform_and_propagate(self, **kwargs)
            if response.public:
                self._save_to_cache(response)
        else:
            # small hack for x-accel-redirect support
            if content is True:
                content = None
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
        self.cache_relative_path = relative_path
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
                if cherrypy.config.get('local.cache.x_accel_redirect.enabled'):
                    cherrypy.response.headers['x-accel-redirect'] = cherrypy.config['local.cache.x_accel_redirect.prefix'] + self.cache_relative_path
                    content = True
                else:
                    content = tools.file.read(self.cache_absolute_path)
                return content
    
    def _save_to_cache(self, response):
        if self.cache_absolute_path is None or response.code is not None:
            return
        
        headers = response.headers
        expires_at = self._determine_response_expiration_time(response)
        if expires_at is not None:
            headers['x-expires-timestamp'] = expires_at
            dir = os.path.dirname(self.cache_absolute_path)
            if not os.path.exists(dir):
                tools.file.safe_mkdirs(dir)
            tools.file.safe_write(self.cache_absolute_path, response.content)
            tools.file.safe_write(self.cache_absolute_path_meta, pickle.dumps(headers))
