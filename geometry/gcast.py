from functools import wraps

def gcastr(obj):
	"""Cast a Geometry3D object to a G* object if one exists."""
	from .gpoint import GPoint
	from .gsegment import GSegment
	from .ghalfline import GHalfLine
	try:
		return locals()['G' + obj.__class__.__name__](obj)
	except KeyError:
		if obj is not None and not obj.__class__.__name__.startswith('G'):
			print(f'Type G{obj.__class__.__name__} not in locals():')
			print([k for k in locals() if k[0] != '_'])
		return obj


def gcast(f):
	@wraps(f)
	def wrapper(*args, **kwargs):
		return gcastr(f(*args, **kwargs))
	return wrapper
