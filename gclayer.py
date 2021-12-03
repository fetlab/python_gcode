from gcline import Line

class Layer():
	def __init__(self, lines=[], layernum=None):
		self.layernum  = layernum
		self.preamble  = []
		self.lines     = lines
		self.postamble = []


	def __repr__(self):
		#If this layer contains some X/Y moves, print the extents
		if any(l for l in self.lines if 'X' in l.args and 'Y' in l.args):
			ex1, ex2 = self.extents()
			return '<Layer %s at Z=%s; corners: (%d, %d), (%d, %d); %d lines>' % (
					(self.layernum, self.z()) + ex1 + ex2 + (len(self.lines),))
		#Otherwise don't!
		return '<Layer {} at Z={}; {} lines; no moves>'.format(
				self.layernum, self.z(), len(self.lines))


	def lineno(self, number):
		"""Return the line with the specified line number."""
		return next((l for l in self.lines if l.lineno == number), None)


	def extents(self):
		"""Return the extents of the layer: the min/max in x and y that
		occur. Note this does not take arcs into account."""
		min_x = min(self.lines, key=lambda l: l.args.get('X', float('inf'))).args['X']
		min_y = min(self.lines, key=lambda l: l.args.get('Y', float('inf'))).args['Y']
		max_x = max(self.lines, key=lambda l: l.args.get('X', float('-inf'))).args['X']
		max_y = max(self.lines, key=lambda l: l.args.get('Y', float('-inf'))).args['Y']
		return (min_x, min_y), (max_x, max_y)
	

	def last_coord(self):
		"""Return the last coordinate moved to."""
		#(X, Y) and Z are probably on different lines.
		x, y, z = None, None, None
		for l in self.lines[::-1]:
			if l.code == 'G28':   #home
				return 0, 0, 0
			if l.code in ('G0', 'G1'):
				x = x or l.args.get('X')
				y = y or l.args.get('Y')
				z = z or l.args.get('Z')
				if x and y and z:
					break
		return x, y, z


	def extents_gcode(self):
		"""Return two Lines of gcode that move to the extents."""
		(min_x, min_y), (max_x, max_y) = self.extents()
		return Line(code='G0', args={'X': min_x, 'Y': min_y}),\
					 Line(code='G0', args={'X': max_x, 'Y': max_y})


	@property
	def z(self):
		"""Return the first Z height found for this layer. It should be
		the only Z unless it's been messed with, so returning the first is
		safe."""
		try:
			return self._z
		except AttributError:
			for l in self.lines:
				if 'Z' in l.args:
					self._z = l.args['Z']
					return self._z


	def set_preamble(self, gcodestr):
		"""Insert lines of gcode at the beginning of the layer."""
		self.preamble = [Line(l) for l in gcodestr.split('\n')]


	def set_postamble(self, gcodestr):
		"""Add lines of gcode at the end of the layer."""
		self.postamble = [Line(l) for l in gcodestr.split('\n')]


	def find(self, code):
		"""Return all lines in this layer matching the given G code."""
		return [line for line in self.lines if line.code == code]


	def shift(self, **kwargs):
		"""Shift this layer by the given amount, applied to the given
		args. Operates by going through every line of gcode for this layer
		and adding amount to each given arg, if it exists, otherwise
		ignoring."""
		for line in self.lines:
			for arg in kwargs:
				if arg in line.args:
					line.args[arg] += kwargs[arg]


	def multiply(self, **kwargs):
		"""Same as shift but with multiplication instead."""
		for line in self.lines:
			for arg in kwargs:
				if arg in line.args:
					line.args[arg] *= kwargs[arg]


	def construct(self):
		"""Construct and return a gcode string."""
		return '\n'.join(l.construct() for l in self.preamble + self.lines
				+ self.postamble)
