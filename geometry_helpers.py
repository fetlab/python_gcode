import Geometry3D
from pint.registry_helpers import check
from functools import wraps
from units import *

def unitwrapper(obj):
	@wraps(obj)
	def wrapper(*args, **kwargs):
		print(f'Doing {obj.__name__}!')
		return obj(*args, **kwargs)
	return wrapper

length = ureg.get_dimensionality('[length]')
angle  = 0*ureg.degrees
# class Point(Geometry3D.Point):
# 	__init__ = check(
