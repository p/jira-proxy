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

def get_umask():
    # python does not provide a way to just read umask apparently
    umask = os.umask(0777)
    os.umask(umask)
    return umask
