from Geometry3D import Circle, Vector
from math import degrees, cos, radians, sin

from gcline import GCLine
from geometry import GPoint
from util import attrhelper

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
		self.center        = center or GPoint(radius, 0, 0)
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
	y = property(**attrhelper('center.y'))
	z = property(**attrhelper('center.z'))


	def __repr__(self):
		return f'Ring({self._angle:.2f}°, {self.center})'


	def attr_changed(self, attr, old_value, new_value):
		# TODO: when we get a y coordinate, need to shift the center of the ring by
		# -y, which also means modifying self.geometry, so that thread_intersect()
		# will properly rotate the ring to maintain the thread trajectory
		if attr == 'y':
			mv = Vector(0, new_value - old_value, 0)
			self.center.move(mv)
			self.geometry.move(mv)
		else:
			raise ValueError(f"Can't adjust the {attr} coordinate of the ring!")


	@property
	def angle(self):
		return self._angle


	@angle.setter
	def angle(self, new_pos:degrees):
		self.set_angle(new_pos)


	@property
	def point(self):
		return self.angle2point(self.angle)


	def set_angle(self, new_angle:degrees, direction=None):
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


	def angle2point(self, angle:degrees):
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


