import os, os.path

def read(path):
    '''Reads file located at path'''
    
    with open(path) as f:
        return f.read()

def _generate_temporary_path(path):
    import tempfile
    
    # todo: fd is an open file descriptor, but tmp_path will be opened again later
    fd, tmp_path = tempfile.mkstemp(prefix=path+'.tmp.')
    return tmp_path

def safe_write(path, content):
    '''Writes content to a temporary file in path's directory,
    then atomically renames temporary file to path'''
    
    tmp_path = _generate_temporary_path(path)
    try:
        with open(tmp_path, 'w') as f:
            f.write(content)
        os.rename(tmp_path, path)
    except:
        # use a separate function to create a new scope,
        # so that we can reraise original exception without holding on to backtrace object.
        # http://docs.python.org/library/sys.html#sys.exc_info
        safe_unlink(tmp_path)
        raise

def safe_write_gzip(path, content):
    '''Writes content compressed with gzip to a temporary file in path's directory,
    then atomically renames temporary file to path'''
    
    import gzip, contextlib
    
    tmp_path = _generate_temporary_path(path)
    try:
        # gzip.open defaults to compresslevel 9, but specify it explicitly in case default changes
        with contextlib.closing(gzip.open(tmp_path, 'w', 9)) as f:
            f.write(content)
            os.rename(tmp_path, path)
    except:
        # use a separate function to create a new scope,
        # so that we can reraise original exception without holding on to backtrace object.
        # http://docs.python.org/library/sys.html#sys.exc_info
        safe_unlink(tmp_path)
        raise

def safe_unlink(path):
    '''Unlinks path, suppressing any exceptions'''
    
    try:
        os.unlink(path)
    except:
        # ignore to propagate original exception
        pass

_mkdirs_lock = None

def safe_mkdirs(path):
    '''Creates directories up to and including path,
    ensuring that two threads do not attempt to create these directories simultaneously'''
    
    global _mkdirs_lock
    
    if _mkdirs_lock is None:
        import threading
        
        _mkdirs_lock = threading.Lock()
    
    _mkdirs_lock.acquire()
    try:
        if not os.path.exists(path):
            os.makedirs(path)
    finally:
        _mkdirs_lock.release()
