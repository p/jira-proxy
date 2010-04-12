import os.path, sys, cherrypy

root = os.path.join(os.path.dirname(__file__), '..')
#sys.path.append(root)

from issues import environment

environment.load_config(root)
environment.setup(root)
