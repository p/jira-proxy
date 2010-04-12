import cherrypy, re

from base_proxy import BaseProxy

class Proxy(BaseProxy):
    default_remote_host = cherrypy.config['remote.host']
    
    reverse_host_map = {
        'tracker.phpbb.com': '',
    }
    
    def __init__(self):
        BaseProxy.__init__(self)
        
        self.html_comment_re = re.compile(r'<!--.*?-->', re.S)
        self.html_script_re = re.compile(r'<script.*?</script>', re.S)
    
    def perform(self, **kwargs):
        BaseProxy.perform(self, **kwargs)
        
        self._massage_remote_response()
    
    def _massage_remote_response(self):
        r = self._remote_response
        
        # kill no-cache and no-store directives, but note whether response was private or not.
        # private responses are not saved to disk later
        r.private = False
        if r.headers.has_key('pragma'):
            value = r.headers['pragma']
            if value == 'no-cache':
                del r.headers['pragma']
                r.private = True
        if r.headers.has_key('cache-control'):
            value = r.headers['cache-control']
            parts = [part.strip() for part in value.split(',')]
            new_parts = [part for part in parts if part not in ['no-cache', 'no-store']]
            if len(parts) != len(new_parts):
                if 'private' not in new_parts:
                    new_parts.append('private')
                new_value = ', '.join(new_parts)
                r.headers['cache-control'] = new_value
                r.private = True
        # quick hack: kill old expiration dates from private responses, without parsing dates
        if r.private and r.headers.has_key('expires'):
            del r.headers['expires']
        
        if r.headers['content-type'].lower().startswith('text/html'):
            content = r.content
            content = self.html_comment_re.sub('', content)
            search = cherrypy.config['remote.host']
            replace = cherrypy.request.headers.get('host') or self.__class__.default_remote_host
            content = content.replace(search, replace)
            #content = self.html_script_re.sub(lambda match: match.group(0).replace(search, replace), content)
            r.content = content
        
        return
        try:
            del r.headers['cache-control']
        except:
            pass
        try:
            del r.headers['expires']
        except:
            pass
