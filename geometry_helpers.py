import Geometry3D
from Geometry3D import Point, Segment, intersection
from pint.registry_helpers import check
from functools import wraps
from units import *
from gcline import Line
from dataclasses import make_dataclass
from copy import deepcopy

Geometry = make_dataclass('Geometry', ['segments', 'planes'])
Planes   = make_dataclass('Planes',   ['top', 'bottom'])


class GCodeException(Exception):
	def __init__(self, obj, message):
		self.obj = obj
		self.message = message


#---- Add as2d() methods to default geometry

@patch
def as2d(self:Point):
	return Point(self.x, self.y, 0)

@patch
def as2d(self:Segment):
	return Segment(self.start_point.as2d(), self.end_point.as2d())


class HalfLine(Geometry3D.HalfLine):
	def __init__(self, a, b):
		self._a = a
		self._b = b
		super().__init__(a, b)


	def as2d(self):
		if not isinstance(self._b, Point):
			raise ValueError(f"Can't convert {type(self._b)} to 2D")
		return Geometry3D.HalfLine(
				GPoint.as2d(self._a),
				GPoint.as2d(self._b))

# ----


class GPoint(Geometry3D.Point):
	def __init__(self, *args):
		"""Pass Geometry3D.Point arguments or a gcline.Line and optionally a *z*
		argument. If *z* is missing it will be set to 0."""
		if len(args) == 1 and isinstance(args[0], Line):
			l = args[0]
			if not (l.code in ('G0', 'G1') and 'X' in l.args and 'Y' in l.args):
				raise ValueError(f"Line instance isn't an X or Y move:\n\t{args[0]}")
			super().__init__(l.args['X'], l.args['Y'], args.get('z', args.get('Z', 0)))
			self.line = l
		else:
			super().__init__(*args)
			self.line = None


	def as2d(self):
		"""Return a copy of this point with *z* set to 0."""
		c = deepcopy(self)
		c.z = 0
		return c



class GSegment(Geometry3D.Segment):
	def __init__(self, line1:Line, line2:Line, z=0):
		a = Point(line1, z=z)
		b = Point(line2, z=z)

		#Copied init code to avoid the deepcopy operation
		if a == b:
			raise ValueError("Cannot initialize a Segment with two identical Points")
		self.line = Geometry3D.Line(a,b)
		self.start_point = a
		self.end_point = b


	def intersection2d(self, other):
		return Geometry3D.intersection(self.as2d(), other.as2d())



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
