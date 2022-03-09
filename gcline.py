import re, sys
from functools import total_ordering
from collections import UserList
from copy import copy

class GCLines(UserList):
	"""Represent a collection of gcode lines with easy access to line numbers."""
	def __init__(self, data=None):
		data = data or []
		super().__init__(data)
		self._generate_index()

	def _generate_index(self):
		"""Create an index relating the given GCLine line number to its index in the
		underlying data structure."""
		self._index = {l.lineno: i for i,l in enumerate(self.data)}


	def __getitem__(self, lineno):
		if isinstance(lineno, slice):
			r = []
			for i in range(lineno.start, lineno.stop, lineno.step or 1):
				try:
					r.append(self.data[self._index[i]])
				except KeyError:
					r.append(None)
			return r
		else:
			try:
				return self.data[self.index(lineno)]
			except KeyError as e:
				raise IndexError(f'GCLine number {lineno} not in GCLines') from e


	def __delitem__(self, lineno):
		try:
			del(self.data[self.index(lineno)])
			del(self._index[lineno])
		except KeyError:
			raise IndexError(f'GCLine number {lineno} not in GCLines')


	#One-line functions
	def __iter__    (self):         return iter(self.data)
	def __contains__(self, lineno): return lineno in self._index
	def index       (self, lineno): return self._index[lineno]
	def remove      (self, line):   del(self[line.lineno])


	def popidx(self, idx):
		"""Pop from the underlying data."""
		line = self.data.pop(idx)
		del(self._index[line.lineno])
		return line


	def append(self, line):
		self.data.append(line)
		self._index[line.lineno] = len(self.data)


	def reverse(self):
		self.data.reverse()
		self._generate_index()


	def sort(self, **kwargs):
		self.data.sort(**kwargs)
		self._generate_index()


	#Convenience methods to avoid having to use .data
	@property
	def first(self): return self.data[0]
	@property
	def last (self): return self.data[-1]

	def start(self, is_extrude=False):
		"""Return the first X/Y move in this group of GCLines"""
		test = GCLine.is_xyextrude if is_extrude else GCLine.is_xymove
		try:
			return next(filter(test, self.data))
		except StopIteration:
			raise ValueError('No X/Y moves in this group')


	def end(self, is_extrude=False):
		"""Return the last X/Y move in this group of GCLines"""
		test = GCLine.is_xyextrude if is_extrude else GCLine.is_xymove
		try:
			return next(filter(test, reversed(self.data)))
		except StopIteration:
			raise ValueError('No X/Y moves in this group')




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
		"""Return a copy of this line without extrusion."""
		c = copy(self)
		del(c.args['E'] #TODO


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
