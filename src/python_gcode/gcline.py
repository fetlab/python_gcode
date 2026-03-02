from __future__ import annotations
import re
from functools import total_ordering
from fastcore.basics import ifnone
from collections import UserList
from gcode_geom import GPoint, GSegment
from gcode_geom.angle import Angle
from .util import deep_update, ReadOnlyDict

from rich.console import Console
rprint = Console(style="on #272727").print

#Use total_ordering to allow comparing based on line number
@total_ordering
class GCLine:
	def __init__(self, line='', lineno:int|str='', code=None, args={}, comment=None, fake=False, meta=None):
		"""Parse a single line of gcode into its code and named
		arguments."""
		self.line    = line.strip()
		self.lineno  = lineno
		self.code    = code.upper() if code else None
		self.args    = args or {}
		self.comment = comment
		self.fake    = fake       #Set to True if it's been generated
		self.meta    = meta or {} #Metadata about this line

		assert not any(isinstance(arg, Angle) for arg in args.values())

		self.relative_extrude = None

		#Comment-only or empty line
		if not self.code and self.line in ('', ';'):
			return

		if ';' in line:
			cmd, cmt = line.split(';', maxsplit=1)
			cmd = cmd.strip()
			if not self.comment:
				self.comment = cmt.strip()
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
									self.args[arg[0]] = arg[1:]
							else:
								self.args[arg[0]] = None
						else:
							self.args[None] = arg

		if not (self.comment or self.code):
			raise ValueError(f'Missing a code for line: "{self}"')

		self.args = ReadOnlyDict(self.args)


	def copy(self, add_comment='', **kwargs):
		"""Return a copy of this line. Pass kwargs to override
		attributes. Specify add_comment to append an additional comment to the
		existing one."""
		comment = kwargs.get('comment', self.comment or '')
		if isinstance(comment,     (list,tuple)): comment     = ' '.join(comment)
		if isinstance(add_comment, (list,tuple)): add_comment = ' '.join(add_comment)
		if add_comment: comment = ' '.join((comment, add_comment))
		gcline = GCLine(
				line    = kwargs.get('line',    self.line if not kwargs else ''),
				lineno  = kwargs.get('lineno',  self.lineno),
				code    = kwargs.get('code',    self.code),
				args    = deep_update(dict(self.args), kwargs.get('args', {})),
				comment = comment,
				fake    = kwargs.get('fake',    self.fake),
				meta    = kwargs.get('meta',    self.meta),
		)
		gcline.relative_extrude = self.relative_extrude
		return gcline


	def __hash__(self):
		return hash(('GCLine', self.lineno, self.construct()))


	def __eq__(self, other):
		return hash(self) == hash(other)


	def __lt__(self, other):
		return self.lineno < other.lineno


	def __repr__(self):
		return self.construct()


	@property
	def is_move(self):
		"""Return True if it's a move in some axis (using Marlin's definition which
		includes X Y Z A B C U V W), else False."""
		return self.code in ('G0', 'G1') and any(ax in self.args for ax in 'XYZABCUVW')


	@property
	def is_xymove(self):
		"""Return True if it's a move in the X/Y plane, else False."""
		return self.code in ('G0', 'G1') and ('X' in self.args or 'Y' in self.args)


	@property
	def is_extrude(self):
		"""Return True if this is an extruding command."""
		return self.code in ('G0', 'G1') and 'E' in self.args


	@property
	def is_xyextrude(self):
		"""Return True if it's an extruding move in the X/Y plane, else False."""
		return self.is_xymove and 'E' in self.args


	def as_xymove(self, fake=False):
		"""Return a copy of this line without extrusion, turning it into a G0."""
		if not self.is_xymove:
			raise ValueError(f'Call of as_xymove() on non-xymove GCLine {self}')
		new_line = self.copy(
			code='G0', args=self.args, fake=fake,
			lineno=self.lineno if not fake else '',
			add_comment='Converted to xy move' + f' (fake from [{self.lineno}])' if fake else '',
		)

		#Remove extrusion command if it exists
		new_args = dict(new_line.args)
		new_args.pop('E', None)
		new_line.args = ReadOnlyDict(new_args)

		return new_line


	@property
	def x(self): return self.args.get('X', None)
	@property
	def y(self): return self.args.get('Y', None)
	@property
	def z(self): return self.args.get('Z', None)
	@property
	def xy(self): return self.x, self.y
	@property
	def xyz(self): return self.x, self.y, self.z


	def construct(self, lineno_in_comment:bool=True, **kwargs) -> str:
		"""Construct and return a line of gcode based on self.code, self.args, and
		self.comment. Pass kwargs to override this line's existing arguments."""
		args = self.args
		if kwargs:
			args = self.args.copy()
			args.update(kwargs)
		out = []

		if self.code:
			out.append(self.code)
		for arg, val in args.items():
			out.append(
					(arg or "") +
					("" if val is None
							else str(round(val, 5))         if isinstance(val, (int,float))
							#else str(round(val.degrees, 5)) if isinstance(val, Angle)
							else val))

		comment = ' '.join([
				f'[{self.lineno}]' if (lineno_in_comment and self.lineno) else '',
				self.comment or '']).strip()
		if comment:
			out.append(f'; {comment}')

		return ' '.join(out)


	def as_record(self):
		"""Return a representation of this line as a Pandas-compatible record
		dict."""
		columns = 'lineno, code, X, Y, Z, E, F, S, comment, original'
		r = {k:'' for k in columns.split(', ')}
		r.update(self.args)
		r['lineno']   = self.lineno
		r['code']     = self.code
		r['comment']  = self.comment
		r['original'] = self.line
		return r



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
			except KeyError as ex:
				raise IndexError(f'GCLine number {to_get} not in GCLines') from ex

		else:
			#Support slicing, including slicing by list
			r, missing = [], []
			fetch = to_get

			if isinstance(to_get, slice):
				#Account for slicing with empty values: list[:10] or list[10:]
				s = to_get.start if to_get.start is not None else self.lineno_min()
				e = to_get.stop  if to_get.stop  is not None else self.lineno_max()

				if s is None or e is None:
					return GCLines()

				if s < self.lineno_min() or e > self.lineno_max():
					rprint('[yellow]Warning: '
							f'Requested slice {s}--{e or "end"} is out of range '
							f'for available lines {self.lineno_min()}--{self.lineno_max()}.')
					s = max(s, self.lineno_min())
					e = min(e, self.lineno_max())

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
		self._generate_index()


	def __setitem__(self, lineno, line:GCLine):
		self.data[self._index[lineno]] = line

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
	def lineno_min  (self):         return min(self._index.keys() or [None])
	def lineno_max  (self):         return max(self._index.keys() or [None])


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


	def start(self, is_extrude=False) -> GCLine|None:
		"""Return the first X/Y (extruding) move in this group of GCLines or None
		if no moves are present."""
		test = GCLine.is_xyextrude if is_extrude else GCLine.is_xymove
		return next(filter(test, self.data), None)


	def end(self, is_extrude=False) -> GCLine|None:
		"""Return the last X/Y (extruding) move in this group of GCLines or None
		if no moves are present."""
		test = GCLine.is_xyextrude if is_extrude else GCLine.is_xymove
		return next(filter(test, reversed(self.data)), None)


	def construct(self):
		return '\n'.join([l.construct() for l in self])


def comment(comment):
	return GCLine(fake=True, comment=comment)


def comments(comments) -> list[GCLine]:
	from textwrap import dedent
	if isinstance(comments, (list,tuple)):
		return [comment(line) for line in comments]
	return [comment(line) for line in dedent(comments).split('\n') if line]


def split_gcline(start:GPoint, line:GCLine, at:GPoint) -> list[GCLine]:
	"""Split `line` at point `at`. Provide `start` as a GCLine or a GPoint
	indicating where the print head was immediately previous to the the line that
	should be split. This is necessary to calculate how much extrusion should be
	alloted to each part of the split."""
	if not line.is_move:
		raise ValueError("Can't split a non-movement line!")

	#Make an ending point, assuming that if a movement value is missing from
	# `line` that it's the same as that value for `start`.
	end = GPoint(
			ifnone(line.x, start.x),
			ifnone(line.y, start.y),
			ifnone(line.z, start.z))

	#Make a GSegment for convenience in lengths and checking that `at` is a valid
	# split location.
	seg = GSegment(start, end)

	if at not in seg:
		raise ValueError(f"Requested split location {at} isn't on segment {seg}")

	#If the line is an extruding one, we have to update the 'E' args for each
	# split accordingly.
	if line.is_extrude:
		#If the line has the `relative_extrude` property and it's not the same as
		# the E argument, then the gcode is in absolute extrusion mode.
		if line.relative_extrude is not None:
			if line.relative_extrude != line.args['E']:
				s1e = line.args['E'] - line.relative_extrude * at.distance(end) / seg.length
				s2e = line.args['E']

			#If they are the same, then the gcode is in relative extrusion mode
			else:
				s1e = line.args['E'] * start.distance(at) / seg.length
				s2e = line.args['E'] - s1e

		#If there is no `relative_extrude` property, we don't know if it's relative
		# or absolute, but have no previous extrusion value to base judgement on,
		# so we have to bail.
		else:
			raise ValueError("No `relative_extrude` propery for line, can't update extrusion value.")

	#First split: starts at `start` (implicit) and ends at `at`.
	# Copy all the args from `line` then replace destination X/Y with `at`,
	# and update the extrusion amount if needed.
	split1 = line.copy(args={'X': at.x, 'Y': at.y, **({'E':s1e} if s1e else {})},
										 add_comment='(split 1)')

	#Second split: starts at `at` and ends where `line` ended. Update extrusion.
	split2 = line.copy(args=({'E':s2e} if s2e else {}), add_comment='(split 2)')

	return [split1, split2]
