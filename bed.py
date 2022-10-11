from geometry import GPoint
from plot_helpers import update_figure

class Bed:
	"""A class representing the print bed."""
	#Default plotting style
	style = {
			'bed': {'line': dict(color='rgba(0,0,0,0)'),
							'fillcolor': 'LightSkyBlue',
							'opacity':.25,
						 },
	}

	def __init__(self, anchor=(0, 0, 0), size=(220, 220)):
		"""Anchor is where the thread is initially anchored on the bed. Size is the
		size of the bed. Both are in mm."""
		self.anchor = GPoint(*anchor)
		self.size   = size

		#Current gcode coordinates of the bed
		self.x      = 0
		self.y      = 0


	def __repr__(self):
		return f'Bed({self.x}, {self.y}, ⚓︎{self.anchor})'


	def plot(self, fig, style=None):
		fig.add_shape(
			name='bed',
			type='rect',
			xref='x',                 yref='y',
			x0=self.x,                y0=self.y,
			x1=self.x + self.size[0], y1=self.y + self.size[1],
			**self.style['bed'],
		)
		update_figure(fig, 'bed', style, what='shapes')

