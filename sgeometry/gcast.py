from functools import wraps
from . import *

def gcast(f):
	@wraps(f)
	def wrapper(*args, **kwargs):
		return _gcast(f(*args, **kwargs))


def _gcast(obj):
	"""Cast a skgeom object to a G* object"""
	try:
		return globals()['G' + obj.__class__.__name__[:-1]](obj)
	except KeyError:
		if obj is not None:
			print(f'Type G{obj.__class__.__name__[:-1]} not in globals():')
			print([k for k in globals() if k[0] != '_'])
		return obj
