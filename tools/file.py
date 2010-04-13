import os, os.path

def read(path):
    '''Reads file located at path'''
    
    with open(path) as f:
        return f.read()

def safe_write(path, content):
    '''Writes content to a temporary file in path's directory,
    then atomically renames temporary file to path'''
    
    import tempfile, contextlib
    
    fd, tmp_path = tempfile.mkstemp(prefix=path+'.tmp.')
    try:
        # calling close() on file object opened with os.fdopen closes the file descriptor
        with contextlib.closing(os.fdopen(fd, 'w')) as f:
            f.write(content)
            # mkstemp creates files with 600 permissions
            os.fchmod(fd, 0666 & ~get_umask())
    except:
        # use a separate function to create a new scope,
        # so that we can reraise original exception without holding on to backtrace object.
        # http://docs.python.org/library/sys.html#sys.exc_info
        safe_unlink(tmp_path)
        raise
    os.rename(tmp_path, path)

def safe_write_gzip(path, content):
    '''Writes content compressed with gzip to a temporary file in path's directory,
    then atomically renames temporary file to path'''
    
    import tempfile, gzip, contextlib
    
    fd, tmp_path = tempfile.mkstemp(prefix=path+'.tmp.')
    try:
        # calling close() on file object opened with os.fdopen closes the file descriptor
        with contextlib.closing(os.fdopen(fd, 'w')) as f:
            # gzip.open defaults to compresslevel 9, but specify it explicitly in case default changes
            with contextlib.closing(gzip.GzipFile(fileobj=f, mode='w', compresslevel=9)) as gz:
                gz.write(content)
            # mkstemp creates files with 600 permissions
            os.fchmod(fd, 0666 & ~get_umask())
    except:
        # use a separate function to create a new scope,
        # so that we can reraise original exception without holding on to backtrace object.
        # http://docs.python.org/library/sys.html#sys.exc_info
        safe_unlink(tmp_path)
        raise
    os.rename(tmp_path, path)

def safe_unlink(path):
    '''Unlinks path, suppressing any exceptions'''
    
    try:
        os.unlink(path)
    except:
        # ignore to propagate original exception
        pass

def safe_mkdirs(path):
    '''Creates directories up to and including path,
    accounting for the possibility that another thread or process may be
    simultaneously attempting to create some of these directories'''
    
    last_message = None
    retries = 5
    while True:
        try:
            if not os.path.exists(path):
                os.makedirs(path)
            break
        except OSError, e:
            import errno
            
            # immediately bail on everything but possible
            # concurrency errors
            if e.errno != errno.EEXIST:
                raise
            
            # makedirs silences EEXIST errors for parent paths of path,
            # but propagates EEXIST errors for path itself.
            # we are not going to rely on this fact, although as long as
            # it holds we are guaranteed to break on the second iteration
            # in the worst case.
            # impose a limit on the number of iterations
            # in case something strange is going on
            retries -= 1
            if retries <= 0:
                raise
            
            # if we made it this far we'll try creating the path again,
            # on the assumption that another process beat us to some
            # or all required directories

_last_umask = 0777
_umask_lock = None

def get_umask():
    '''Retrieves current umask.
    
    Care is taken to be thread-friendly, but due to umask system call changing umask
    files created in other threads (native code?) while this function runs could get wrong umask.
    
    A safe way to use get_umask to retrieve umask that is not changed during process lifetime
    is as follows:
    
    1. When the process is initializing, and is single-threaded, call get_umask to setup
    umask cache.
    
    2. As long as umask is not changed, future get_umask calls are guaranteed to not actually
    alter umask.
    
    get_umask temporarily sets umask to 777 on the first call, and on subsequent calls to
    the value returned by the previous call.
    '''
    
    global _last_umask, _umask_lock
    
    if _umask_lock is None:
        import threading
        
        _umask_lock = threading.Lock()
    
    _umask_lock.acquire()
    try:
        _last_umask = os.umask(_last_umask)
        os.umask(_last_umask)
    finally:
        _umask_lock.release()
    
    return _last_umask
