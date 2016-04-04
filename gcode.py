import re, sys

class Line(object):
	def __init__(self, line):
		"""Parse a single line of gcode into its code and named
		arguments."""
		self.line = line

		#Extract the comment if there is one
		lc = self.line.split(';', 1)
		if len(lc) > 1:
			self.line, self.comment = lc
		else:
			self.comment = None

		#Get the actual code and the arguments
		args = self.line.split()
		self.code = args[0]
		self.args = {}
		if self.code == 'M117':
			self.args[None] = self.line.split(None, 1)[1]
		else:
			for arg in args[1:]:
				if re.match('[A-Za-z]', arg[0]):
					try:
						self.args[arg[0]] = float(arg[1:]) if '.' in arg[1:] else int(arg[1:])
					except ValueError:
						sys.stderr.write("Line: %s\n" % line)
						raise
				else:
					self.args[None] = arg


	def __repr__(self):
		return self.construct()
		return '%s: %s' % (self.code, repr(self.args))


	def construct(self):
		"""Construct and return a line of gcode based on self.code and
		self.args."""
		return ' '.join([self.code] + ['%s%s' % (k if k else '', v) for k,v in
			self.args.items()]) + (' ;%s' % self.comment if self.comment else '')



class Layer(object):
	def __init__(self, lines, layernum=None):
		"""Parse a layer of gcode line-by-line, making Line objects."""
		self.layernum  = layernum
		self.preamble  = []
		self.lines     = [Line(l) for l in lines if l and l[0] != ';']
		self.postamble = []


	def __repr__(self):
		return '<Layer %s at Z=%s, %d lines>' % (self.layernum, self.z(),
				len(self.lines))


	def z(self):
		"""Return the first Z height found for this layer. It should be
		the only Z unless it's been messed with, so returning the first is
		safe."""
		for l in self.lines:
			if 'Z' in l.args:
				return l.args['Z']


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


		


class Gcode(object):
	def __init__(self, filestring):
		"""Parse a file's worth of gcode passed as a string. Example:
		  g = Gcode(open('mycode.gcode').read())"""
		self.preamble = None
		self.layers   = []
		self.parse(filestring)


	def __repr__(self):
		return '<Gcode with %d layers>' % len(self.layers)


	def construct(self):
		"""Construct and return all of the gcode."""
		s = (self.preamble.construct() + '\n') if self.preamble else ''
		for i,layer in enumerate(self.layers):
			s += ';LAYER:%d\n' % i
			s += layer.construct()
			s += '\n'
		return s


	def shift(self, layernum=0, **kwargs):
		"""Shift given layer and all following. Provide arguments and
		amount as kwargs. Example: shift(17, X=-5) shifts layer 17 and all
		following by -5 in the X direction."""
		for layer in self.layers[layernum:]:
			layer.shift(**kwargs)


	def multiply(self, layernum=0, **kwargs):
		"""The same as shift() but multiply the given argument by a
		factor."""
		for layer in self.layers[layernum:]:
			layer.multiply(**kwargs)


	def parse(self, filestring):
		"""Parse the gcode."""
		in_preamble = True

		#Cura nicely adds a "LAYER" comment just before each layer
		if ';LAYER:' in filestring:
			#Split into layers
			splits = re.split(r'^;LAYER:\d+\n', filestring, flags=re.M)
			self.preamble = Layer(splits[0].split('\n'), layernum=0)
			self.layers = [Layer(l.split('\n'), layernum=i) for i,l in
					enumerate(splits[1:])]
	
		#Sliced with Slic3r, so no LAYER comments; we have to look for
		# G0 or G1 commands with a Z in them
		else:
			layernum = 1
			for l in filestring.split('\n'):
				curr_layer = []

				#Looks like a layer change because we have a Z
				if re.match(r'G[01]\s.*Z-?\.?\d+', l):
					if in_preamble:
						self.preamble = Layer(curr_layer, layernum=0)
						in_preamble = False
					else:
						self.layers.append(Layer(curr_layer, layernum=layernum))
						layernum =+ 1
					curr_layer = [l]

				#Not a layer change so add it to the current layer
				else:
					curr_layer.append(l)

			self.layers.append(Layer(curr_layer))
