from skgeom import Point3, Vector3
from fastcore.basics import properties
from .gbase import _GBase

class GPoint(Point3, _GBase):
	def __init__(self, *args, **kwargs):
		"""Pass Geometry3D.Point arguments or a gcline.GCLine and optionally a *z*
		argument. If *z* is missing it will be set to 0."""
		self.line = None
		z = kwargs.get('z', 0) or 0

		if len(args) == 1:
			#Using type() rather than isinstance() to avoid circular import issues
			if type(args[0]).__name__ == 'GCLine':
				l = args[0]
				if not (l.code in ('G0', 'G1') and 'X' in l.args and 'Y' in l.args):
					raise ValueError(f"GCLine instance isn't an X or Y move:\n\t{args[0]}")
				super().__init__(l.args['X'], l.args['Y'], z)
				self.line = l

			elif isinstance(args[0], (list,tuple)):
				super().__init__(args[0])

			elif isinstance(args[0], Point3):
				super().__init__(
					kwargs.get('x', args[0].x),
					kwargs.get('y', args[0].y),
					kwargs.get('z', args[0].z))

			else:
				raise ValueError(f'Invalid type for arg to GPoint: ({type(args[0])}) {args[0]}')

		elif len(args) == 2:
			super().__init__(*args)

		elif len(args) == 3:
			super().__init__(*args)

		else:
			raise ValueError(f"Can't init GPoint with args {args}")


	def __repr__(self):
		return "{{{:>6.2f}, {:>6.2f}, {:>6.2f}}}".format(*map(float, self[:]))


	def __hash__(self):
		return hash(('Point3', float(self.x), float(self.y), float(self.z)))


	def set_z(self, z):
		if z == self.z: return self
		return self.__class__(
				self.x,
				self.y,
				self.z if z is None else z)


	def moved(self, vec: Vector3):
		"""Return a copy of this point moved by vector vec."""
		return self.__class__(
				self.x + vec.x,
				self.y + vec.y,
				self.z + vec.z)
