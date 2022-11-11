"""This is the specific Ender 3 Pro we have and its parameters:

	- the bed moves for the y axis (XZ gantry)
	- at (0,0) the bed is all the way towards the rear of the printer and the
		print head is at the extreme left
	- printable bed size is 220x220
	- actual bed size is 235x235
	- in X, the bed is centered on the frame coordinate system

	We'll use the X/Y parts of the Fusion 360 model's coordinate system as the
	X/Y for the base printer coordinate system, so (0, 0) is centered above one
	of the bolts on the bottom of the printer. Note that in Fusion the model is
	oriented with Y up and Z towards the front of the printer, but I'm switching
	coordinates here so that Z is up and Y is towards the back.

	Looking straight down from the top of the printer, x=0 is at the center of
	the top cross-piece of the printer, and y=0 is at the top/back edge of that
	piece. We'll set z=0 as the bed surface (in the Fusion model this is at
	z=100.964 mm above the table surface, but in real life is at 100 mm).

	By this coordinate system then (verified by measuring):
	* Bed (0,0,0) = (-117.5, -65, 0)
	* Ring
		* (0,0) = (5, -37)

Ring configuration:
	- ring is fixed to the x-axis gantry
	- ring y center (nearly) matches the center of the x-axis gantry bar, which
		is 1 in towards the rear from the center of the nozzle
	- ring x center is 130 mm from left z-axis gantry, or 122.5 mm from bed x = 0

Bed configuration:
	The actual printable bed area is very restricted by the print head's ability
	to move on the x-axis within the ring. Thus, its effective size should be
	79 x 220. On the actual printer, the effective width as measured by moving the
	heat and seeing where the nozzle hits the bed is 77.5 mm, with the left side
	of this area at 85 mm from the left edge of the bed.

	Thus, the new origin for the bed, in the printer frame coordinate system, is
	then (-32.5, -65, 0). This is when the bed is at y=0, with the front edge of
	the bed plate underneath the nozzle. When the bed is at its other extreme,
	with the back edge of the plate under the nozzle, then the actual front-left
	corner of the bed is at (-32.5, -285).

Print head configuration:
	The print head moves in X/Z; for our purposes, we only care about X, where
	we use the bed coordinates.

Transforms to provide:
	The point is that when we have a move, we want to know the actual path of the
	thread between the carrier and the print head. So there is a transform
	between the head (bed) coordinate and the ring coordinate, complicated by the
	fact that the bed moves in the y-axis.
"""

from printer import Printer
from geometry import GPoint, GSegment
from Geometry3D import Vector
from gcline import GCLine
from typing import TypedDict
from util import Number, Saver

# --- Ring gearing ---
steps_per_rotation = 200 * 16   #For the stepper motor; 16 microsteps
motor_gear_teeth   = 30
ring_gear_teeth    = 125

#Set to -1 if positive E commands make the ring go clockwise
rot_mul = 1  # 1 since positive steps make it go CCW

#How many motor steps per CCW degree?
# Use this with M92 to set steps per unit
esteps_per_degree = steps_per_rotation * ring_gear_teeth / motor_gear_teeth / 360


# --- Actual measured parameters of the printer, in the coordinate system of
# the printer frame (see comments above) ---
BedConfig = TypedDict('BedConfig', {'zero': GPoint, 'size': tuple[Number, Number]})
RingConfig = TypedDict('RingConfig', {'zero': GPoint, 'radius': Number, 'esteps': Number, 'rot_mul': Number})

bed_config: BedConfig = {
	'zero': GPoint(-32.5, -65, 0),
	'size': (77.5, 220),
}
ring_config: RingConfig = {
	'zero': GPoint(5, -37, 0),
	'radius': 93,   #effective thread radius from thread carrier to ring center
	'esteps': esteps_per_degree,
	'rot_mul': 1,
}



class Ender3(Printer):
	def __init__(self):
		super().__init__(bed_config['size'], ring_config['radius'])
		self.ring2bed = Vector(ring_config['zero'], bed_config['zero'])

	@property
	def bed2ring(self): return -self.ring2bed


	def attr_changed(self, attr, old_value, new_value):
		"""When the y coordinate of the printer changes, this means that the bed
		has moved relative to the ring. Thus we update the vector that transforms a
		ring coordinate into the coordinate system of the bed."""
		if attr == '_y':
			self.ring2bed = Vector(ring_config['zero'], bed_config['zero'].copy(y=new_value))


	def anchor_to_ring(self) -> GSegment:
		"""Return a GSegment in Bed coordinates that represents the path between
		the current anchor and the ring."""
		return GSegment(self.anchor, self.ring.point.moved(self.ring2bed), z=self.z)



	def execute_gcode(self, gcline:GCLine) -> list[GCLine]:
		#If the bed moves, we need to update the ring angle to track it
		lines: list[GCLine] = []
		if gcline.is_xyextrude():
			self.x = gcline.args['X']
			self.y = gcline.args['Y']   #This triggers attr_changed, which will change the ring2bed vector
			thread = self.anchor_to_ring()
			isecs = self.ring.intersection(thread)
			angle = self.ring.point2angle(isecs[-1])
			if angle != self.ring.angle:
				self.ring.angle = angle

				save_vars = 'extruder_no', 'extrusion_mode'
				with Saver(self, save_vars) as saver:
					for rline in self.ring.gcode_move():
						if any(rline == saver.saved[var] for var in save_vars):
							continue
						lines.extend(super().execute_gcode(rline))
					if lines[-1].code == 'G1':
						lines[-1].comment += f' for Y={self.y}'

				#Restore extruder state if it was changed
				for var in saver.changed:
					super().execute_gcode(saver.saved[var])
					lines.append(saver.saved[var])

		#Put the input line of gcode last, so we execute it after we move the ring
		lines.append(gcline)
		return lines
