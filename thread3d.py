"""
Goal: add gcode to control pusher bsased on thread location.
"""
import gcode
import matplotlib.pyplot as plt
from matplotlib.path import Path
import matplotlib.patches as patches
import sg_helper as sgh


class TLayer(gcode.Layer):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.threads = []
		self.chunks  = []

		self.parse_moves()


	def parse_moves(self):
		"""Parse the moves in this layer into contiguous chunks."""
		chunks = []
		cur = []
		for l in self.lines:
			if l.is_xymove():
				if l.args.get('E', -1) > 0:   #An extrusion
					cur.append(l)
				else:  #A movement command
					if len(cur) > 0:
						chunks.append(cur)
					cur = []
		if len(cur) > 0:
			chunks.append(cur)

		self.chunks = chunks


	def plot(self, *args, **kwargs):
		"""Plot the layer."""
		verts = []
		codes = []
		lines = iter(self.lines)
		l = next(lines)

		#Find the first location and move to it
		while not l.is_xymove():
			l = next(lines)
		verts.append((l.args['X'], l.args['Y']))
		codes.append(Path.MOVETO)

		#Now parse the rest to create the drawing sequence
		for l in lines:
			if l.is_xymove():
				verts.append((l.args['X'], l.args['Y']))
				if l.args.get('E', -1) > 0:
					codes.append(Path.LINETO)
				else:
					codes.append(Path.MOVETO)

		path = Path(verts, codes)
		if 'fig' in kwargs and 'ax' in kwargs:
			fig = kwargs['fig']
			ax = kwargs['ax']
		else:
			fig, ax = plt.subplots()
		patch = patches.PathPatch(path, fc='none', lw=kwargs.get('lc', 2),
			ec=kwargs.get('ec', 'b'))
		ax.add_patch(patch)

		(min_x, min_y), (max_x, max_y) = self.extents()
		ax.set_xlim(min_x - 1, max_x + 1)
		ax.set_ylim(min_y - 1, max_y + 1)

		ax.set_aspect('equal')

		self.fig = fig
		self.ax  = ax


	def set_thread(self, x=None, y=None):
		"""Add a thread and draw it."""
		if x:
			y1, y2 = self.ax.get_ylim()
			self.threads = [sgh.Segment2((x, y1), (x, y2))]
			self.ax.plot((x,x), (y1,y2), 'r', lw=.5)
		elif y:
			x1, x2 = self.ax.get_xlim()
			self.threads = [sgh.Segment2((x1, y), (x2, y))]
			self.ax.plot((x1, x2), (y,y), 'r', lw=.5)
