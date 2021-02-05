import re, sys, warnings, math, os
import gcode_docs as _gcode_docs

gcode_docs = _gcode_docs.GCodeDocs()

class GCLine():
	def __init__(self, line='', lineno='', code=None, args={}, comment=None):
		"""Parse a single line of gcode into its code and named
		arguments."""
		self.line    = line.strip()
		self.lineno  = lineno
		self.code    = code.upper() if code else None
		self.args    = args or {}
		self.comment = comment
		self.empty   = False

		if (args or code) and (not (args and code)):
			raise ValueError("Both code and args must be specified: got\n"
			"{}, {} for line\n{}".format(code, args, line))

		#Comment-only or empty line
		if not self.code and self.line in ('', ';'):
			self.empty = True
			return

		if ';' in line:
			cmd, cmt = re.match('^(.*?)\s*;\s*(.*?)\s*$', line).groups()
			self.comment = cmt
		else:
			cmd = line

		if cmd: #Not a comment-only line
			#Get the actual code and the arguments
			parts = cmd.split(maxsplit=1)
			self.code = parts[0].upper()

			if len(parts) > 1:
				#Special case for setting message on LCD, no named args
				if self.code == 'M117':
					self.args[None] = parts[1]
				else:
					#Process the rest of the arguments
					for arg in parts[1].split():
						if re.match('[A-Za-z]', arg[0]):
							if arg[1:] is not None and arg[1:] != '':
								try:
									self.args[arg[0]] = float(arg[1:]) if '.' in arg[1:] else int(arg[1:])
								except ValueError:
									sys.stderr.write("GCLine: %s\n" % line)
									raise
							else:
								self.args[arg[0]] = None
						else:
							self.args[None] = arg


	def __repr__(self):
		r = '[{}] '.format(self.lineno) if self.lineno else ''
		return r + self.construct() 


	def is_xymove(self):
		"""Return True if it's a move in the X/Y plane, else False."""
		return self.code in ('G0', 'G1') and ('X' in self.args or 'Y' in self.args)


	def construct(self):
		"""Construct and return a line of gcode based on self.code,
		self.args, and self.comment."""
		if self.empty:
			return self.line

		out = []
		if self.code:
			out.append(self.code)
		out.extend(['{}{}'.format(k, v) for k,v in self.args.items()])
		if self.comment:
			out.append('; ' + self.comment)

		return ' '.join(out)


	def doc(self):
		"""Print documentation about the code in this line, if any."""
		if self.code:
			gcode_docs.pdoc(self.code)



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
		"""Return two GCLines of gcode that move to the extents."""
		(min_x, min_y), (max_x, max_y) = self.extents()
		return GCLine(code='G0', args={'X': min_x, 'Y': min_y}),\
					 GCLine(code='G0', args={'X': max_x, 'Y': max_y})


	def z(self):
		"""Return the first Z height found for this layer. It should be
		the only Z unless it's been messed with, so returning the first is
		safe."""
		for l in self.lines:
			if 'Z' in l.args:
				return l.args['Z']


	def set_preamble(self, gcodestr):
		"""Insert lines of gcode at the beginning of the layer."""
		self.preamble = [GCLine(l) for l in gcodestr.split('\n')]


	def set_postamble(self, gcodestr):
		"""Add lines of gcode at the end of the layer."""
		self.postamble = [GCLine(l) for l in gcodestr.split('\n')]


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



class GcodeFile():
	def __init__(self, filename=None, filestring='', layer_class=Layer):
		"""Parse a file's worth of gcode."""
		self.preamble = None
		self.layers   = []
		self.filestring = filestring
		if filename:
			if filestring:
				warnings.warn("Ignoring passed filestring in favor of loading file.")
			self.filestring = open(filename).read()
		self.filelines = self.filestring.split('\n')
		self.layer_class = layer_class
		self.parse()


	def __repr__(self):
		return '<GcodeFile with %d layers>' % len(self.layers)


	def construct(self, outfile=None):
		"""Construct all of and return the gcode. If outfile is given,
		write the gcode to the file instead of returning it."""
		s = (self.preamble.construct() + '\n') if self.preamble else ''
		for i,layer in enumerate(self.layers):
			s += ';LAYER:%d\n' % i
			s += layer.construct()
			s += '\n'
		if outfile:
			with open(outfile, 'w') as f:
				f.write(s)
		else:
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


	def parse(self):
		"""Parse the gcode. Split it into chunks of lines at Z changes,
		assuming that denotes layers. The Layer object does the actual
		parsing of the code."""
		if not self.filelines:
			return

		#First, just parse each line of gcode as-is
		self.lines = [GCLine(l, lineno=n) for n,l in enumerate(self.filelines)]

		#Attempt to detect what generated the gcode so we can use that
		# program's hints to split into layers.
		#PrusaSlicer: has header comment "generated by PrusaSlicer", has
		# "BEFORE_LAYER_CHANGE" and "AFTER_LAYER_CHANGE" comments,
		# although these are configured per-printer in .ini files. Looks
		# like new layers start at "BEFORE_LAYER_CHANGE".
		#Simplify3D: has header comment "generated by Simplify3D", has
		# comments "layer N" where N is a number.
		#Cura 15: has footer comment "CURA_PROFILE_STRING", has comments
		# "LAYER:N" where N is a number.
		#Cura 4.6: has header comment "Generated with Cura_SteamEngine",
		# has comment "LAYER:N" where N is a number.
		#Slic3r 1.3: has header comment "generated by Slic3r", no comments
		# to denote layer changes

		variant = 'Z' #Default: find layers by Z-height changes
		splitter = None
		if 'PrusaSlicer' in self.filestring[:1000]:
			variant = 'PrusaSlicer'
			splitter = "AFTER_LAYER_CHANGE"
		elif 'Simplify3D' in self.filestring[:1000]:
			variant = 'Simplify3D'
			splitter = r'layer \d+'
		elif 'CURA_PROFILE_STRING' in self.filestring[:-1000]:
			variant = 'Cura15'
			splitter = r'LAYER:\d+'
		elif 'Cura_SteamEngine' in self.filestring[:1000]:
			variant = 'Cura4.6'
			splitter = r'LAYER:\d+'

		layer_num = -1
		curr_layer = []

		if variant is not None:
			for l in self.lines:
				if re.search(splitter, l.line):  #End of layer
					#Next: get the coordinates of the previous layer's final move
					self.layers.append(self.layer_class(curr_layer, layer_num))
					curr_layer = []
					layer_num += 1
				else:
					curr_layer.append(l)

	
		"""
		#Sliced with Slic3r, so no LAYER comments; we have to look for
		# G0 or G1 commands with a Z in them. PrusaSlicer (and Slic3r?)
		# seems to have mid-layer jumps, so we need to assume that a layer
		# also has an extrusion (E) command in it.
		else:
			layernum = 1
			curr_layer = []
			lines = self.filestring.split('\n')
			for l in lines:
				#Count line numbers and generate a 0-padded string for the
				# line number
				linenum += 1
				linestr = '{:0>{width}}'.format(linenum,
					width=int(math.log10(len(lines)))+1)

				#Looks like a possible layer change because we have a Z
				if re.match(r'G[01]\s.*Z-?\.?\d+', l):
					if in_preamble:
						self.preamble = Layer(curr_layer, layernum=0)
						in_preamble = False
						curr_layer = [(linestr, l)]
					else:
						#Check to see if there was any extrusion; if not, assume
						# not a real layer change
						if any(re.search(r'E\d', x[1]) for x in curr_layer):
							self.layers.append(Layer(curr_layer, layernum=layernum))
							layernum =+ 1
							curr_layer = [(linestr, l)]

				#Not a layer change so add it to the current layer
				else:
					curr_layer.append((linestr, l))

			self.layers.append(Layer(curr_layer))
		"""


if __name__ == "__main__":
	if sys.argv[1:]:
		g = GcodeFile(sys.argv[1])
		print(g)
		print((g.layers))
