import cherrypy, urllib, urllib2, Cookie, cookielib, time, urlgrabber.keepalive

class BaseParameters:
    def __init__(self):
        self.host = self.path = self.method = self.params = self.data = self.query_string = self.cookie = self.headers = None

class BaseResponse:
    def __init__(self, **kwargs):
        self.params = self.code = self.content = self.raw_response = None
        
        self.headers = {}
        self.cookies = cookielib.CookieJar()
        
        for key, value in kwargs.items():
            setattr(self, key, value)

class BaseProxy:
    ParametersClass = BaseParameters
    ResponseClass = BaseResponse
    default_remote_host = None
    reverse_host_map = None
    
    class NoRedirectHandler(urllib2.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            return None
    
    PASS_REMOTE_HEADERS = ('content-type', 'content-disposition', 'location', 'cache-control', 'pragma', 'expires')
    
    def __init__(self):
        self._create_opener()
    
    def _create_opener(self):
        if cherrypy.config.get('debug.http_requests'):
            import httplib
            httplib.HTTPConnection.debuglevel = 1
        handlers = []
        handlers.append(urlgrabber.keepalive.HTTPHandler())
        handlers.append(self.__class__.NoRedirectHandler())
        self._opener = urllib2.build_opener(*handlers)
        user_agent = cherrypy.config.get('remote.user_agent')
        if user_agent:
            self._opener.addheaders = [('user-agent', user_agent)]
    
    def perform(self, **kwargs):
        self._collect_request_parameters(**kwargs)
        self._create_remote_request()
        self._issue_remote_request()
        self._rewrite_host_in_location()
    
    def perform_and_propagate(self, **kwargs):
        self.perform(**kwargs)
        self._propagate_remote_response()
        return self._remote_response
    
    def _collect_request_parameters(self, **kwargs):
        parameters = self.__class__.ParametersClass()
        host = kwargs.get('host') or self.__class__.default_remote_host
        if host is None:
            raise ValueError('host not specified by client and no default provided')
        parameters.host = host
        parameters.path = kwargs.get('path_info') or cherrypy.request.path_info
        parameters.method = kwargs.get('method') or cherrypy.request.method.lower()
        
        if parameters.method == 'post':
            parameters.params = kwargs.get('params') or cherrypy.request.params
            parameters.data = urllib.urlencode(parameters.params)
            if kwargs.get('params_in_qs'):
                parameters.query_string, parameters.data = parameters.data, None
            else:
                parameters.query_string = None
        else:
            parameters.params = kwargs.get('params') or cherrypy.request.params
            parameters.query_string = urllib.urlencode(parameters.params)
            parameters.data = None
        
        if cherrypy.request.headers.has_key('Cookie'):
            parameters.cookie = cherrypy.request.headers['Cookie']
        else:
            parameters.cookie = None
        
        parameters.headers = {}
        
        self._params = parameters
    
    def _create_remote_request(self):
        params = self._params
        if params.query_string:
            query_string_append = '?' + params.query_string
        else:
            query_string_append = ''
        headers = dict(params.headers)
        if params.cookie:
            headers['Cookie'] = params.cookie
        self._remote_request = urllib2.Request('http://' + params.host + params.path + query_string_append, params.data, headers)
    
    def _issue_remote_request(self):
        try:
            response = self._opener.open(self._remote_request)
            response_code = None
        except urllib2.HTTPError, e:
            response = e
            response_code = e.code
        
        self._remote_response = self.__class__.ResponseClass(params=self._params, code=response_code, content=response.read(), raw_response=response)
        
        remote_info = response.info()
        
        for key, value in remote_info.items():
            if key in self.__class__.PASS_REMOTE_HEADERS:
                self._remote_response.headers[key.lower()] = value
        
        self._remote_response.cookies.extract_cookies(response, self._remote_request)
    
    def _rewrite_host_in_url(self, url):
        if self.reverse_host_map is None:
            return url
        
        prefix = 'http://'
        if url.startswith(prefix):
            work_url = url[len(prefix):]
            for src, dest in self.reverse_host_map.items():
                search = src + '/'
                if work_url.startswith(search):
                    if dest:
                        new_url = prefix + dest + work_url[len(src):]
                    else:
                        new_url = work_url[len(src):]
                    return new_url
        return url
    
    def _rewrite_host_in_location(self):
        if self._remote_response.headers.has_key('location'):
            location = self._remote_response.headers['location']
            new_location = self._rewrite_host_in_url(location)
            if location != new_location:
                self._remote_response.headers['location'] = new_location
    
    def _propagate_remote_response(self):
        r = self._remote_response
        if r.code:
            cherrypy.response.status = r.code
        
        for key, value in r.headers.items():
            cherrypy.response.headers[key] = value
        
        cookies = Cookie.SimpleCookie()
        # time returns a float, however Cookie code only converts integer offsets to rfc-formatted times
        now = int(time.time())
        for cookie in r.cookies:
            cookies[cookie.name] = cookie.value
            morsel = cookies[cookie.name]
            if cookie.secure:
                morsel['secure'] = cookie.secure
            if cookie.path:
                morsel['path'] = cookie.path
            # forums don't set expiration date on cookie
            if cookie.expires:
                # cookielib's cookies have expires as time since epoch;
                # Cookie's cookies expect expires as time since now
                morsel['expires'] = cookie.expires - now
            if cookie.get_nonstandard_attr('httponly', False) != False:
                morsel['httponly'] = cookie.get_nonstandard_attr('httponly')
        cherrypy.response.cookie = cookies
