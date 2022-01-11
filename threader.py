import plotly.graph_objects as go
from copy import deepcopy
from fastcore.basics import *
from Geometry3D import Segment, Point, intersection
from math import radians, sin, cos


class Ring:
	_style = {
		'ring': {line: dict(color='white', width=10)},
		'indicator': {line: dict(color='blue', width=2)},
	}
	__repr__ = basic_repr('diameter,angle,center')

	def __init__(self, radius=110, angle: radians=0, center: Point=(110,110,0), style: dict=None):
		store_attr(but='style', cast=True)
		self.style = deepcopy(self._style)
		if style is not None:
			for item in style:
				self.style[item].update(style[item])


	def carrier_location(self, offset=0):
		return Point(
			self.center.x + cos(self.angle)*(self.radius+offset),
			self.center.y + sin(self.angle)*(self.radius+offset),
		)


	def plot(self, fig):
		fig.add_shape(
			name='ring',
			type='circle',
			xref='x', yref='y',
			x1=self.center.x-self.diameter/2,
			y1=self.center.y-self.diameter/2,
			x2=self.center.x+self.diameter/2,
			y2=self.center.y+self.diameter/2,
			**self.style['ring'],
		)
		c1 = self.carrier_location()
		c2 = self.carrier_location(offset=3)
		fig.add_shape(
			name='ring_indicator',
			type='line',
			xref='x', yref='y',
			x1=c1.x, y1=c1.y,
			x2=c2.x, y2=c2.y,
			**self.style['indicator'],
		)


class Bed:
	__repr__ = basic_repr('anchor_location,size')

	def __init__(self, anchor_location=(0,0), size=(220, 220)):
		store_attr()



class Router:
	__repr__ = basic_repr('bed,ring')

	def __init__(self, bed, ring):
		store_attr()
		self.anchor = Point(bed.anchor_location[0], bed.anchor_location[1], 0)

	def thread(self):
		"""Return a Segment representing the current thread, from the anchor point to the ring."""
		#TODO: account for bed location (y axis)
		return Segment(self.anchor, self.ring.carrier_location())
