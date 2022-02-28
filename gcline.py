import re, sys

class Line():
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


	def __hash__(self):
		return hash(f'{self.lineno} {self.line}')


	def __repr__(self):
		r = '[{}] '.format(self.lineno) if self.lineno else ''
		return r + self.construct()


	def is_xymove(self):
		"""Return True if it's a move in the X/Y plane, else False."""
		return self.code in ('G0', 'G1') and ('X' in self.args or 'Y' in self.args)


	def is_xyextrude(self):
		"""Return True if it's an extruding move in the X/Y plane, else False."""
		return self.is_xymove() and 'E' in self.args


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


# def doc(self):
# 	"""Print documentation about the code in this line, if any."""
# 	if self.code:
# 		gcode_docs.pdoc(self.code)
