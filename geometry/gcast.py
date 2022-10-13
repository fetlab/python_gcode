from .gpoint import GPoint
from .gsegment import GSegment
from .ghalfline import GHalfLine

def gcast(obj):
	"""Cast a Geometry3D object to a G* object if one exists."""
	try:
		return globals()['G' + obj.__class__.__name__](obj)
	except KeyError:
		if obj is not None:
			print(f'Type G{obj.__class__.__name__} not in globals():')
			print([k for k in globals() if k[0] != '_'])
		return obj
