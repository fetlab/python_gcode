from Geometry3D import Circle, Vector
from math import degrees, cos, radians, sin
from typing import Tuple, List

from gcline import GCLine
from geometry import GPoint, GSegment, GHalfLine
from geometry.gcast import gcast
from geometry.utils import eq2d
from util import attrhelper
from logger import rprint

from plot_helpers import update_figure

class Ring:
	"""A class representing the ring and thread carrier."""
	#Default plotting style
	style = {
		'ring':      {'line': dict(color='white', width=10), 'opacity':.25},
		'indicator': {'line': dict(color='blue',  width= 4)},
	}

	#TODO: add y-offset between printer's x-axis and ring's x-axis
	def __init__(self, radius=100, angle=0, center:GPoint=None):
		self.radius        = radius
		self._angle        = angle
		self.initial_angle = angle
		self.center        = GPoint(radius, 0, 0) if center is None else GPoint(center).copy()
		self.geometry      = Circle(self.center, Vector.z_unit_vector(), self.radius, n=100)

		#Defaults for rotating gear
		steps_per_rotation  = 200 * 16   #For the stepper motor; 16 microsteps
		motor_gear_teeth    = 30
		ring_gear_teeth     = 125

		#Set to -1 if positive E commands make the ring go clockwise
		self.rot_mul        = 1  # 1 since positive steps make it go CCW

		#How many motor steps per degree?
		self.esteps_degree = int(
			steps_per_rotation * ring_gear_teeth / motor_gear_teeth / 360)

	x = property(**attrhelper('center.x'))
	z = property(**attrhelper('center.z'))


	def __repr__(self):
		return f'Ring(⌀{self.radius*2}, {self._angle:.2f}°, {self.center})'

	@property
	def y(self): return self.center.y

	@y.setter
	def y(self, val):
		if val == self.center.y: return
		mv = Vector(0, val - self.center.y, 0)
		self.center.move(mv)
		self.geometry.move(mv)


	def attr_changed(self, attr, old_value, new_value):
		raise ValueError(f"Can't adjust the {attr} coordinate of the ring!")


	@property
	def angle(self):
		return self._angle


	@angle.setter
	def angle(self, new_pos):
		self.set_angle(new_pos)


	@property
	def point(self):
		return self.angle2point(self.angle)


	def intersection(self, seg:GSegment|GHalfLine) -> List[GPoint]:
		"""Return the intersection points between the passed GSegment and the ring,
		sorted by distance to seg.start_point ."""
		#Form a half line (basically a ray) from the anchor through the target
		hl = (seg if isinstance(seg, GHalfLine) else GHalfLine(seg.start_point, seg.end_point)).as2d()

		#isecs = filter(None, map(hl.intersection, self.ring.geometry.segments))

		isecs = hl.intersections(self.geometry.segments())
		if isecs is None: return []

		#The intersection is always a Segment; we want to sort by distance to the
		# input segment, but avoiding the start point of the segment.
		return sorted(isecs, key=lambda p: seg.start_point.distance(p))


	def set_angle(self, new_angle, direction=None):
		"""Set a new angle for the ring. Optionally provide a preferred movement
		direction as 'CW' or 'CCW'; if None, it will be automatically determined."""
		self.initial_angle = self._angle
		self._angle = new_angle
		self._direction = direction


	def carrier_location(self, offset=0):
		"""Used in plotting."""
		return GPoint(
			self.center.x + cos(radians(self.angle))*(self.radius+offset),
			self.center.y + sin(radians(self.angle))*(self.radius+offset),
			self.center.z
		)


	def angle2point(self, angle):
		"""Return an x,y,z=0 location on the ring based on the given angle, without
		moving the ring. Assumes that the bed's bottom-left corner is (0,0).
		Doesn't take into account a machine that uses bed movement for the y-axis,
		but just add the y value to the return from this function."""
		return GPoint(
			cos(radians(angle)) * self.radius + self.center.x,
			sin(radians(angle)) * self.radius + self.center.y,
			self.center.z
		)


	def gcode_move(self):
		"""Return the gcode necessary to move the ring from its current angle
		to its requested one."""
		#Were there any changes in angle?
		if self.angle == self.initial_angle:
			return []

		#Find "extrusion" amount - requires M92 has set steps/degree correctly
		dist = self.angle - self.initial_angle
		dir_mul = -1 if ((dist+360)%360 < 180) else 1  #Determine CW/CCW rotation
		extrude = self.rot_mul * dist * dir_mul

		gc = ([
			GCLine(code='T1', comment='Switch to ring extruder', fake=True),
			GCLine(code='M82', comment='Set relative extrusion mode', fake=True),
			GCLine(code='G1', args={'E':round(extrude,3), 'F':8000},
				comment=f'Ring move from {self.initial_angle:.2f}° to {self.angle:.2f}°', fake=True),
		])

		self._angle = self.initial_angle
		return gc


	def plot(self, fig, style=None):
		fig.add_shape(
			name='ring',
			type='circle',
			xref='x', yref='y',
			x0=self.center.x-self.radius, y0=self.center.y-self.radius,
			x1=self.center.x+self.radius, y1=self.center.y+self.radius,
			**self.style['ring'],
		)
		update_figure(fig, 'ring', style, what='shapes')

		ringwidth = next(fig.select_shapes(selector={'name':'ring'})).line.width

		c1 = self.carrier_location(offset=-ringwidth/2)
		c2 = self.carrier_location(offset=ringwidth/2)
		fig.add_shape(
			name='indicator',
			type='line',
			xref='x', yref='y',
			x0=c1.x, y0=c1.y,
			x1=c2.x, y1=c2.y,
			**self.style['indicator'],
		)
		update_figure(fig, 'indicator', style, what='shapes')


