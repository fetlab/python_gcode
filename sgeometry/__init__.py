import typing, skgeom as sg
from skgeom import Point2, Vector2, Segment2, Line2, \
									 Point3, Vector3, Segment3, Line3
from fastcore.basics import properties, patch

from .ghalfline import GHalfLine
from .gpoint    import GPoint
from .gsegment  import GSegment

# --- Patch skgeom classes with useful tools
POINT_TYPES = Point2 | Point3
LINE_TYPES  = Vector2 | Segment2 | Vector3 | Segment3 | Line2 | Line3

Point2._x  = Point2.x;  Point2.x  = property(Point2._x)
Point2._y  = Point2.y;  Point2.y  = property(Point2._y)
Point3._x  = Point3.x;  Point3.x  = property(Point3._x)
Point3._y  = Point3.y;  Point3.y  = property(Point3._y)
Point3._z  = Point3.z;  Point3.z  = property(Point3._z)
Vector2._x = Vector2.x; Vector2.x = property(Vector2._x)
Vector2._y = Vector2.y; Vector2.y = property(Vector2._y)
Vector3._x = Vector3.x; Vector3.x = property(Vector3._x)
Vector3._y = Vector3.y; Vector3.y = property(Vector3._y)
Vector3._z = Vector3.z; Vector3.z = property(Vector3._z)

##Set up obj.x etc as properties, keep functions as _x()
#for t in (Point2, Point3, Vector2, Vector3):
#	for a in 'xyz'[:int(t.__name__[-1])]:
#		setattr(t, f'_{a}', getattr(t, a))
#		setattr(t, a, property(getattr(t, f'_{a}')))


for t in typing.get_args(POINT_TYPES | LINE_TYPES):
	T = getattr(sg, 'Transformation' + t.__name__[-1])
	t.move  = lambda self, v: self.transform(T(sg.TRANSLATION, v))
	t.scale = lambda self, s: self.transform(T(sg.SCALING, s))


#Add `x in seg`, .length property
for t in typing.get_args(LINE_TYPES):
	if hasattr(t, 'has_on'): t.__contains__ = t.has_on
	t.length = lambda self: float(self.squared_length())**.5



@patch
def __hash__(self: POINT_TYPES | LINE_TYPES):
	return hash((self.__class__.__name__, self[:]))


@patch
def __repr__(self: Point2 | Point3):
	return "!{" + ', '.join('{:>6.2f}'.format(float(c)) for c in self[:]) + "}"


@patch
def __repr__(self: Segment2 | Segment3):
	return "!<{}←→{}>".format(self.source(), self.target())


@patch
def __repr__(self: Vector2 | Vector3):
	return "!<●→{}>".format(self[:])


@patch
def __getitem__(self: Point2 | Point3 | Vector2 | Vector3, idx):
	return tuple(getattr(self, 'xyz'[i]) for i in range(self.dimension()))[idx]


Point3.to_2d   = lambda self: Point2(*self[:2])
Vector3.to_2d  = lambda self: Vector2(*self[:2])
Segment3.to_2d = lambda self: Segment2(self[0].to_2d(), self[1].to_2d())
Line3.to_2d    = lambda self: Line2(self[0].to_2d(), self[1].to_2d())


# --- End patching


__all__ = [
	'GPoint',
	'GSegment',
	'GHalfLine',
]
