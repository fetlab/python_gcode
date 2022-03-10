import re, sys
from functools import total_ordering
from collections import UserList
from copy import copy

from rich.console import Console
rprint = Console(style="on #272727").print

@total_ordering
class GCLine:
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


	def __eq__(self, other):
		return hash(self) == hash(other)


	def __lt__(self, other):
		return self.lineno < other.lineno


	def __repr__(self):
		r = '[{}] '.format(self.lineno) if self.lineno else ''
		return r + self.construct()


	def is_xymove(self):
		"""Return True if it's a move in the X/Y plane, else False."""
		return self.code in ('G0', 'G1') and ('X' in self.args or 'Y' in self.args)


	def is_xyextrude(self):
		"""Return True if it's an extruding move in the X/Y plane, else False."""
		return self.is_xymove() and 'E' in self.args


	def as_xymove(self):
		"""Return a copy of this line without extrusion, turning it into a G0."""
		if not self.is_xymove():
			raise ValueError(f'Call of as_xymove() on non-xymove GCLine {self}')
		c = copy(self)
		if 'E' in c.args:
			del(c.args['E'])
		c.code = 'G0'
		return c


	def construct(self):
		"""Construct and return a line of gcode based on self.code,
		self.args, and self.comment."""
		out = []
		if self.code:
			out.append(self.code)
		out.extend(['{}{}'.format(k, v) for k,v in self.args.items()])
		if self.comment:
			out.append('; ' + self.comment)

		return ' '.join(out)


class GCLines(UserList):
	"""Represent a collection of gcode lines with easy access to line numbers."""
	def __init__(self, data=None):
		data = data or []
		super().__init__(data)
		self._generate_index()


	def _generate_index(self):
		"""Create an index relating the given GCLine line number to its index in the
		underlying data structure."""
		self._index = {}
		for i,l in enumerate(self.data):
			if l.lineno is None or l.lineno == '':
				raise ValueError(f"Can't store GCLine without lineno: {l}")
			self._index[l.lineno] = i


	def __getitem__(self, to_get):
		if not isinstance(to_get, (slice, list, tuple, set)):
			try:
				return self.data[self.index(to_get)]
			except KeyError as e:
				raise IndexError(f'GCLine number {to_get} not in GCLines') from e

		else:
			#Support slicing, including slicing by list
			r, missing = [], []
			fetch = to_get

			if isinstance(to_get, slice):
				#Account for slicing with empty values: list[:10] or list[10:]
				s = to_get.start if to_get.start is not None else self.lineno_min()
				e = to_get.stop  if to_get.stop  is not None else self.lineno_max()

				if s < self.lineno_min() or e > self.lineno_max():
					raise ValueError(' '.join((f'Requested slice {s}--{e or "end"} is out of range',
							f'for available lines {self.lineno_min()}--{self.lineno_max()}.')))

				fetch = range(s, e, to_get.step or 1)

			for i in fetch:
				try:
					r.append(self.data[self._index[i]])
				except KeyError:
					missing.append(i)

			if missing:
				rprint(f'Warning: you requested lines {s}--{e}',
							f'but lines {missing} were not in this object: {self.summary()}')

			return GCLines(r)


	def __delitem__(self, lineno):
		try:
			del(self.data[self.index(lineno)])
			del(self._index[lineno])
		except KeyError:
			raise IndexError(f'GCLine number {lineno} not in GCLines')


	def __repr__(self):
		return f'{self.summary()}\n' + '\n'.join(map(repr, self.data))


	def summary(self):
		n = len(self.data)
		if n == 0:
			return '<GCLines with 0 lines>'
		if n > 1:
			return ' '.join((f'<GCLines with {n} lines from',
											 f'{self.lineno_min()} to {self.lineno_max()}>'))
		return f'<GCLines with 1 line, number {self.lineno_min()}>'


	#One-line functions
	def __iter__    (self):         return iter(self.data)
	def __contains__(self, lineno): return lineno in self._index
	def index       (self, lineno): return self._index[lineno]
	def remove      (self, line):   del(self[line.lineno])
	def lineno_min  (self):         return min(self._index.keys())
	def lineno_max  (self):         return max(self._index.keys())


	def popidx(self, idx):
		"""Pop from the underlying data."""
		line = self.data.pop(idx)
		del(self._index[line.lineno])
		return line


	def extend(self, data):
		self.data.extend(data)
		self._generate_index()


	def append(self, line):
		self.data.append(line)
		self._index[line.lineno] = len(self.data)


	def reverse(self):
		self.data.reverse()
		self._generate_index()


	def sort(self, **kwargs):
		self.data.sort(**kwargs)
		self._generate_index()


	@property
	def first(self) -> GCLine:
		"""Return the first line in this group of GCLines."""
		return self.data[0]


	@property
	def last (self) -> GCLine:
		"""Return the last line in this group of GCLines."""
		return self.data[-1]


	def start(self, is_extrude=False) -> GCLine:
		"""Return the first X/Y (extruding) move in this group of GCLines or None
		if no moves are present."""
		test = GCLine.is_xyextrude if is_extrude else GCLine.is_xymove
		return next(filter(test, self.data), None)


	def end(self, is_extrude=False) -> GCLine:
		"""Return the last X/Y (extruding) move in this group of GCLines or None
		if no moves are present."""
		test = GCLine.is_xyextrude if is_extrude else GCLine.is_xymove
		return next(filter(test, reversed(self.data)), None)




# def doc(self):
# 	"""Print documentation about the code in this line, if any."""
# 	if self.code:
# 		gcode_docs.pdoc(self.code)
