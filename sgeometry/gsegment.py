from skgeom import Point3, Segment3, Vector3
from .gpoint import GPoint
from .gbase import _GBase
from .gcast import _gcast

class GSegment(_GBase):
	def __init__(self, a, b=None, z=None, gc_lines=None, is_extrude=False, **kwargs):
		#Label whether this is an extrusion move or not
		self.is_extrude = is_extrude

		self.printed = False

		#Save the movement lines of gcode
		self.gc_line1 = None
		self.gc_line2 = None

		#Save *all* lines of gcode involved in this segment
		self.gc_lines = gc_lines

		#Argument |a| is a GSegment: instantiate a copy
		if isinstance(a, Segment3):
			# if b is not None:
			# 	raise ValueError('Second argument must be None when first is a Segment')
			copyseg = a
			#Make copies of the start/end points to ensure we avoid accidents
			a = copyseg.start_point
			b = copyseg.end_point
			gc_lines   = getattr(copyseg, 'gc_lines', []) if gc_lines is None else gc_lines
			is_extrude = getattr(copyseg, 'is_extrude', is_extrude)

		#If instantiating a copy, |a| and |b| have been set from the passed GSegment
		if isinstance(a, Point3):
			point1 = GPoint(a)
		elif type(a).__name__ == 'GCLine': #Using type() rather than isinstance() to avoid circular import issues
			point1 = GPoint(a)
			self.gc_line1 = a
			self.gc_lines.append(a)
		elif isinstance(a, (tuple,list)):
			point1 = GPoint(*a)
		else:
			print(a, type(a), type(a) == GSegment)
			raise ValueError("Attempt to instantiate a GSegment with argument |a| as "
					f"type {type(a)}, but only <GSegment>, <Point3>, <GCLine>, <tuple> and <list> are supported.\n"
					" If this occurrs in a Jupyter notebook, it's because reloading messes things up. Try restarting the kernel.")

		if isinstance(b, Point3):
			point2 = GPoint(b)
		elif type(b).__name__ == 'GCLine': #Using type() rather than isinstance() to avoid circular import issues
			point2 = GPoint(b)
			self.gc_line2 = b
			self.gc_lines.append(b)
		elif isinstance(b, (tuple,list)):
			point2 = GPoint(*b)
		else:
			raise ValueError(f"Arg b is type {type(b)} = {b} but that's not supported!")

		if z is not None:
			point1 = point1.set_z(z)
			point2 = point2.set_z(z)

		if point1 == point2:
			raise ValueError("Cannot initialize a Segment with two identical Points\n"
					f"Init args: a={a}, b={b}, z={z}")

		self._start_point = point1
		self._end_point   = point2
		self._segment = Segment3(point1, point2)

		#Sort any gcode lines by line number
		if self.gc_lines:
			self.gc_lines.sort()


	def __repr__(self):
		if not(self.gc_line1 and self.gc_line2):
			return "<{}←→{} ({:.2f} mm)>".format(self.start_point, self.end_point,
					self.length)
		return "<{}[{:>2}] {}:{}←→{}:{} ({:.2f} mm)>".format(
				'S' if self.printed else 's',
				len(self.gc_lines),
				self.gc_line1.lineno, self.start_point,
				self.gc_line2.lineno, self.end_point,
				self.length())


	def __getitem__(self, idx):
		return (self.start_point, self.end_point)[idx]


	def __getattr__(self, attr):
		return getattr(self._segment, attr)


	def __mul__(self, amt):
		if not isinstance(amt, (int, float)):
			raise ValueError(f"Can't multiply by {type(amt)}")
		return self.__class__(self.start_point, self.end_point + self.to_vector() * (amt - 1))


	@property
	def start_point(self): return self._start_point
	@property
	def end_point(self):   return self._end_point


	def as2d(self):
		if self.start_point.z == 0 and self.end_point.z == 0:
			return self
		return GSegment(self.start_point.as2d(), self.end_point.as2d())


	def set_z(self, z):
		"""Set both endpoints of this Segment to a new z."""
		if self.start_point.z == z and self.end_point.z == z: return self
		return self.__class__(self.start_point.copy(z), self.end_point.copy(z))


	def copy(self, start_point=None, end_point=None, z=None):
		return self.__class__(self, None,
			start_point=start_point or self.start_point,
			end_point=end_point     or self.end_point,
			z=z)


	def parallels2d(self, distance=1, inc_self=False):
		"""Return two GSegments parallel to this one, offset by `distance` to either
		side. Include this segment if in_self is True."""
		v = self.line.dv.normalized()
		mv1 = Vector3(v[1], -v[0], v[2]) * distance
		mv2 = Vector3(-v[1], v[0], v[2]) * distance
		return [self.moved(mv1), self.moved(mv2)] + ([self] if inc_self else [])


	@property
	def length(self): return float(self._segment.squared_length())**.5
