from collections.abc import Sequence
from geometry import GPoint
from plot_helpers import update_figure
from Geometry3D import Vector

class Bed:
	"""A class representing the print bed."""
	#Default plotting style
	style = {
			'bed': {'line': dict(color='rgba(0,0,0,0)'),
							'fillcolor': 'LightSkyBlue',
							'opacity':.25,
						 },
	}

	def __init__(self, anchor:Sequence=(0, 0, 0), size:Sequence=(220, 220)):
		"""Anchor is where the thread is initially anchored on the bed. Size is the
		size of the bed. Both are in mm."""
		self.anchor = GPoint(*anchor)
		self.size   = size

		#Current gcode coordinates of the bed
		self.x      = 0
		self.y      = 0


	def __repr__(self):
		return f'Bed({self.x}, {self.y}, ⚓︎{self.anchor})'


	def plot(self, fig, style=None, offset:Vector=None):
		x, y = self.x, self.y
		if offset:
			x += offset._v[0]
			y += offset._v[1]
		fig.add_shape(
			name='bed',
			type='rect',
			xref='x',            yref='y',
			x0=x,                y0=y,
			x1=x + self.size[0], y1=y + self.size[1],
			**self.style['bed'],
		)
		update_figure(fig, 'bed', style, what='shapes')

