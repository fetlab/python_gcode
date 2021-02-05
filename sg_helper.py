"""Subclass various classes from skgeom so we can add properties and
extra attributes, as original classes are immutable."""
import skgeom as sg

def l2p(l):
	"""Turn a 2- or 3-item list/tuple into a sg.Point* object."""
	if isinstance(l, (sg.Point2, sg.Point3)):
		return l
	if len(l) == 2:
		return Point2(*l)
	elif len(l) == 3:
		return Point3(*l)
	raise ValueError("Must have 2 or 3 elements, not {}".format(len(l)))


class Point2(sg.Point2):
	@property
	def x(self):
		return super().x()

	@property
	def y(self):
		return super().y()


class Segment2(sg.Segment2):
	#Allow init with tuple or list, not just Point2
	def __init__(self, *args, **kwargs):
		super().__init__(l2p(args[0]), l2p(args[1]), *args[2:], **kwargs)

	@property
	def x(self):
		return super().x()

	@property
	def y(self):
		return super().y()


class Point3(sg.Point3):
	def __init__(self, *args, **kwargs):
		super().__init__(l2p(args[0]), l2p(args[1]), *args[2:], **kwargs)

	@property
	def x(self):
		return super().x()

	@property
	def y(self):
		return super().y()

	@property
	def z(self):
		return super().z()


class Segment3(sg.Segment3):
	#Allow init with tuple or list, not just Point3
	@property
	def x(self):
		return super().x()

	@property
	def y(self):
		return super().y()

	@property
	def z(self):
		return super().z()
